const TARGET_SAMPLE_RATE = 16000

export class AudioStreamer {
  constructor(websocketUrl, onTextReceived) {
    this.websocketUrl = websocketUrl
    this.onTextReceived = onTextReceived

    this.socket = null
    this.audioContext = null
    this.mediaStream = null

    this.source = null
    this.processor = null
    this.gainNode = null

    this.sourceType = 'system'
  }

  /**
   * sourceType:
   * - system: âm thanh đang phát trong máy tính
   * - microphone: âm thanh từ microphone hoặc loa ngoài
   */
  async start(sourceType = 'system') {
    if (!['system', 'microphone'].includes(sourceType)) {
      throw new Error(`Nguồn âm thanh không hợp lệ: ${sourceType}`)
    }

    this.sourceType = sourceType

    try {
      await this.connectWebSocket()

      if (sourceType === 'microphone') {
        await this.initMicrophoneCapture()
      } else {
        await this.initSystemAudioCapture()
      }
    } catch (error) {
      await this.stop()
      throw error
    }
  }

  /**
   * Kết nối đến backend Python.
   */
  connectWebSocket() {
    return new Promise((resolve, reject) => {
      let isOpened = false
      let hasFinished = false

      this.socket = new WebSocket(this.websocketUrl)
      this.socket.binaryType = 'arraybuffer'

      const timeoutId = window.setTimeout(() => {
        if (hasFinished || isOpened) {
          return
        }

        hasFinished = true

        reject(new Error('Không thể kết nối tới backend trong vòng 5 giây.'))

        if (this.socket) {
          this.socket.close()
        }
      }, 5000)

      this.socket.onopen = () => {
        if (hasFinished) {
          return
        }

        isOpened = true
        hasFinished = true

        window.clearTimeout(timeoutId)

        console.log('✅ Đã kết nối tới Server AI Python!')

        resolve()
      }

      this.socket.onmessage = (event) => {
        if (this.onTextReceived) {
          this.onTextReceived(event.data)
        }
      }

      this.socket.onerror = (error) => {
        console.error('❌ Lỗi WebSocket:', error)

        if (!isOpened && !hasFinished) {
          hasFinished = true
          window.clearTimeout(timeoutId)

          reject(new Error('Không thể kết nối tới backend.'))
        }
      }

      this.socket.onclose = () => {
        window.clearTimeout(timeoutId)

        console.log('🔌 WebSocket đã đóng.')

        if (!isOpened && !hasFinished) {
          hasFinished = true

          reject(new Error('WebSocket bị đóng trước khi kết nối thành công.'))
        }
      }
    })
  }

  /**
   * Thu âm thanh từ microphone.
   *
   * Chế độ này dùng cho:
   * - người nói trực tiếp
   * - âm thanh từ điện thoại
   * - âm thanh đang phát từ loa ngoài
   */
  async initMicrophoneCapture() {
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error('Thiết bị không hỗ trợ truy cập microphone.')
    }

    this.mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,

        /*
         * Thiết bị có thể không trả đúng 16 kHz.
         * Audio sẽ được chuyển về 16 kHz ở bước xử lý.
         */
        sampleRate: TARGET_SAMPLE_RATE,

        /*
         * Tắt khử tiếng vọng để tránh trường hợp Electron
         * loại bỏ âm thanh đang phát từ loa ngoài.
         */
        echoCancellation: false,

        /*
         * Có thể giữ lọc nhiễu và tự động tăng âm lượng
         * để hỗ trợ microphone laptop.
         */
        noiseSuppression: true,
        autoGainControl: true
      },

      video: false
    })

    this.watchMediaTracks()

    await this.setupAudioPipeline()

    console.log('🎤 Đã bắt đầu thu microphone hoặc âm thanh từ loa ngoài.')
  }

  /**
   * Thu trực tiếp âm thanh đang phát bên trong máy tính.
   *
   * Chế độ này dùng cho:
   * - Google Meet
   * - Zoom
   * - Microsoft Teams
   * - YouTube
   * - Video hoặc audio đang phát trong máy
   */
  async initSystemAudioCapture() {
    if (!window.electron?.ipcRenderer) {
      throw new Error('Không tìm thấy Electron IPC Renderer.')
    }

    const sources = await window.electron.ipcRenderer.invoke('get-sources', {
      types: ['screen'],
      thumbnailSize: {
        width: 0,
        height: 0
      }
    })

    if (!sources || sources.length === 0) {
      throw new Error('Không tìm thấy nguồn màn hình để lấy âm thanh.')
    }

    const sourceId = sources[0].id

    this.mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        mandatory: {
          chromeMediaSource: 'desktop',
          chromeMediaSourceId: sourceId
        }
      },

      /*
       * Chromium thường yêu cầu kèm video khi dùng
       * chromeMediaSource để capture desktop.
       *
       * Video chỉ được lấy để tạo MediaStream,
       * không được gửi đến backend.
       */
      video: {
        mandatory: {
          chromeMediaSource: 'desktop',
          chromeMediaSourceId: sourceId,
          maxFrameRate: 1
        }
      }
    })

    const audioTracks = this.mediaStream.getAudioTracks()

    if (audioTracks.length === 0) {
      throw new Error('Nguồn màn hình không cung cấp âm thanh hệ thống.')
    }

    this.watchMediaTracks()

    await this.setupAudioPipeline()

    console.log('🖥 Đã bắt đầu thu âm thanh đang phát trong máy tính.')
  }

  /**
   * Theo dõi khi microphone hoặc nguồn desktop bị dừng.
   */
  watchMediaTracks() {
    if (!this.mediaStream) {
      return
    }

    for (const track of this.mediaStream.getTracks()) {
      track.addEventListener(
        'ended',
        () => {
          console.warn(`⚠️ Track ${track.kind} đã kết thúc.`)
        },
        {
          once: true
        }
      )
    }
  }

  /**
   * Tạo pipeline:
   *
   * MediaStream
   * → AudioContext
   * → chuyển về mono 16 kHz
   * → PCM16
   * → WebSocket
   */
  async setupAudioPipeline() {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext

    if (!AudioContextClass) {
      throw new Error('Thiết bị không hỗ trợ AudioContext.')
    }

    /*
     * Thử tạo AudioContext 16 kHz.
     * Một số thiết bị chỉ hỗ trợ 44.1 hoặc 48 kHz,
     * khi đó sẽ tạo AudioContext mặc định.
     */
    try {
      this.audioContext = new AudioContextClass({
        sampleRate: TARGET_SAMPLE_RATE
      })
    } catch (error) {
      console.warn('Không thể tạo AudioContext 16 kHz, dùng tần số mặc định:', error)

      this.audioContext = new AudioContextClass()
    }

    if (this.audioContext.state === 'suspended') {
      await this.audioContext.resume()
    }

    this.source = this.audioContext.createMediaStreamSource(this.mediaStream)

    /*
     * ScriptProcessor hiện đã cũ nhưng vẫn dùng được
     * cho Proof of Concept Electron này.
     */
    this.processor = this.audioContext.createScriptProcessor(2048, 1, 1)

    this.processor.onaudioprocess = (event) => {
      if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
        return
      }

      const inputData = event.inputBuffer.getChannelData(0)

      const inputSampleRate = event.inputBuffer.sampleRate || this.audioContext.sampleRate

      const samples16Khz = this.resampleAudio(inputData, inputSampleRate, TARGET_SAMPLE_RATE)

      const pcm16 = this.convertFloat32ToPcm16(samples16Khz)

      /*
       * Luôn gửi cả phần có tiếng và khoảng im lặng.
       *
       * Backend cần khoảng im lặng để nhận biết
       * người nói đã kết thúc câu.
       */
      if (pcm16.length > 0 && this.socket.readyState === WebSocket.OPEN) {
        this.socket.send(pcm16.buffer)
      }
    }

    this.source.connect(this.processor)

    /*
     * ScriptProcessor phải nối với destination
     * thì onaudioprocess mới chạy liên tục.
     *
     * Gain bằng 0 nên âm thanh không bị phát lại,
     * tránh tạo tiếng vọng.
     */
    this.gainNode = this.audioContext.createGain()

    this.gainNode.gain.value = 0

    this.processor.connect(this.gainNode)

    this.gainNode.connect(this.audioContext.destination)

    console.log(`🎧 AudioContext đang chạy ở ${this.audioContext.sampleRate} Hz`)
  }

  /**
   * Chuyển audio từ tần số thiết bị về 16 kHz.
   */
  resampleAudio(inputData, inputSampleRate, outputSampleRate) {
    if (!inputData || inputData.length === 0) {
      return new Float32Array(0)
    }

    if (inputSampleRate === outputSampleRate) {
      return new Float32Array(inputData)
    }

    const sampleRateRatio = inputSampleRate / outputSampleRate

    const outputLength = Math.max(1, Math.round(inputData.length / sampleRateRatio))

    const outputData = new Float32Array(outputLength)

    for (let outputIndex = 0; outputIndex < outputLength; outputIndex += 1) {
      const startIndex = Math.floor(outputIndex * sampleRateRatio)

      const endIndex = Math.min(inputData.length, Math.floor((outputIndex + 1) * sampleRateRatio))

      if (endIndex <= startIndex) {
        outputData[outputIndex] = inputData[Math.min(startIndex, inputData.length - 1)]

        continue
      }

      let total = 0

      for (let inputIndex = startIndex; inputIndex < endIndex; inputIndex += 1) {
        total += inputData[inputIndex]
      }

      outputData[outputIndex] = total / (endIndex - startIndex)
    }

    return outputData
  }

  /**
   * Chuyển Float32 từ khoảng -1 đến 1
   * thành PCM signed 16-bit.
   */
  convertFloat32ToPcm16(inputData) {
    const pcm16 = new Int16Array(inputData.length)

    for (let index = 0; index < inputData.length; index += 1) {
      const sample = Math.max(-1, Math.min(1, inputData[index]))

      pcm16[index] = sample < 0 ? Math.round(sample * 0x8000) : Math.round(sample * 0x7fff)
    }

    return pcm16
  }

  /**
   * Dừng toàn bộ audio, WebSocket và MediaStream.
   */
  async stop() {
    if (this.processor) {
      this.processor.onaudioprocess = null

      try {
        this.processor.disconnect()
      } catch (error) {
        console.warn('Không thể ngắt processor:', error)
      }

      this.processor = null
    }

    if (this.source) {
      try {
        this.source.disconnect()
      } catch (error) {
        console.warn('Không thể ngắt source:', error)
      }

      this.source = null
    }

    if (this.gainNode) {
      try {
        this.gainNode.disconnect()
      } catch (error) {
        console.warn('Không thể ngắt gainNode:', error)
      }

      this.gainNode = null
    }

    if (this.mediaStream) {
      this.mediaStream.getTracks().forEach((track) => {
        track.stop()
      })

      this.mediaStream = null
    }

    if (this.audioContext && this.audioContext.state !== 'closed') {
      try {
        await this.audioContext.close()
      } catch (error) {
        console.warn('Không thể đóng AudioContext:', error)
      }

      this.audioContext = null
    }

    if (this.socket) {
      this.socket.onmessage = null
      this.socket.onerror = null
      this.socket.onopen = null
      this.socket.onclose = null

      if (
        this.socket.readyState === WebSocket.OPEN ||
        this.socket.readyState === WebSocket.CONNECTING
      ) {
        this.socket.close()
      }

      this.socket = null
    }

    console.log('⏹ Đã dừng AudioStreamer hoàn toàn.')
  }
}
