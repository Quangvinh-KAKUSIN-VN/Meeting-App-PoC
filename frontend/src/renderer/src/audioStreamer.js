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

    // Chỉ dùng cho microphone
    this.highPassFilter = null
    this.lowPassFilter = null
    this.compressor = null

    this.sourceType = 'system'

    this.platform = window.api?.platform || 'unknown'

    /*
     * Trạng thái noise gate của microphone.
     *
     * Noise gate sẽ gửi dữ liệu bằng 0 khi chỉ có tiếng nền.
     * Khoảng im lặng vẫn được gửi để backend kết thúc câu.
     */
    this.microphoneNoiseFloor = 0.003
    this.microphoneGateOpen = false
    this.microphoneGateHoldRemaining = 0

    // Giữ gate mở thêm một lúc để không cắt cuối từ.
    this.microphoneGateHoldTime = 0.35
  }

  async start(sourceType = 'system') {
    const allowedSources = ['system', 'microphone']

    if (!allowedSources.includes(sourceType)) {
      throw new Error(`Nguồn âm thanh không hợp lệ: ${sourceType}`)
    }

    this.sourceType = sourceType

    this.resetMicrophoneGate()

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
   * Tự thêm loại nguồn âm thanh vào WebSocket:
   *
   * ?source=system
   * ?source=microphone
   *
   * Backend dùng thông tin này để chọn bộ VAD phù hợp.
   */
  getWebSocketUrl() {
    try {
      const url = new URL(this.websocketUrl)

      url.searchParams.set('source', this.sourceType)

      return url.toString()
    } catch {
      const separator = this.websocketUrl.includes('?') ? '&' : '?'

      return `${this.websocketUrl}` + `${separator}source=` + encodeURIComponent(this.sourceType)
    }
  }

  connectWebSocket() {
    return new Promise((resolve, reject) => {
      let hasFinished = false

      const socketUrl = this.getWebSocketUrl()

      console.log(`🔌 Kết nối WebSocket: ${socketUrl}`)

      this.socket = new WebSocket(socketUrl)

      this.socket.binaryType = 'arraybuffer'

      const timeoutId = window.setTimeout(() => {
        if (hasFinished) {
          return
        }

        hasFinished = true

        reject(new Error('Không thể kết nối backend trong vòng 5 giây.'))

        this.socket?.close()
      }, 5000)

      this.socket.onopen = () => {
        if (hasFinished) {
          return
        }

        hasFinished = true

        window.clearTimeout(timeoutId)

        console.log('✅ Đã kết nối tới Backend Python.')

        resolve()
      }

      this.socket.onmessage = (event) => {
        if (this.onTextReceived) {
          this.onTextReceived(event.data)
        }
      }

      this.socket.onerror = (error) => {
        console.error('❌ Lỗi WebSocket:', error)

        if (!hasFinished) {
          hasFinished = true

          window.clearTimeout(timeoutId)

          reject(new Error('Không thể kết nối tới backend.'))
        }
      }

      this.socket.onclose = () => {
        window.clearTimeout(timeoutId)

        console.log('🔌 WebSocket đã đóng.')

        if (!hasFinished) {
          hasFinished = true

          reject(new Error('WebSocket bị đóng trước khi kết nối.'))
        }
      }
    })
  }

  /**
   * Thu âm thanh từ microphone hoặc loa ngoài.
   */
  async initMicrophoneCapture() {
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error('Thiết bị không hỗ trợ microphone.')
    }

    this.mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: {
          ideal: 1
        },

        sampleRate: {
          ideal: TARGET_SAMPLE_RATE
        },

        /*
         * Phải tắt echoCancellation vì ứng dụng
         * cần nghe tiếng phát ra từ loa ngoài.
         *
         * Nếu bật, trình duyệt có thể xem tiếng loa
         * là tiếng vọng và loại bỏ nó.
         */
        echoCancellation: false,

        /*
         * Giữ lọc nhiễu của hệ điều hành.
         */
        noiseSuppression: true,

        /*
         * Quan trọng:
         * Không tự động tăng tiếng quạt, tiếng gõ bàn,
         * tiếng điều hòa khi phòng đang yên lặng.
         */
        autoGainControl: false
      },

      video: false
    })

    const audioTracks = this.mediaStream.getAudioTracks()

    if (audioTracks.length === 0) {
      throw new Error('Không tìm thấy microphone.')
    }

    console.log('🎤 Microphone:', audioTracks[0].label || 'Thiết bị mặc định')

    console.log('🎤 Cấu hình microphone:', audioTracks[0].getSettings())

    this.watchMediaTracks()

    await this.setupAudioPipeline()

    console.log('🎤 Đang nghe microphone hoặc loa ngoài.')
  }

  /**
   * Thu trực tiếp âm thanh đang phát trong máy tính.
   */
  async initSystemAudioCapture() {
    const getSources =
      window.api?.getSources ||
      (window.electron?.ipcRenderer
        ? (options) => window.electron.ipcRenderer.invoke('get-sources', options)
        : null)

    if (!getSources) {
      throw new Error('Không tìm thấy API lấy nguồn màn hình.')
    }

    const sources = await getSources({
      types: ['screen']
    })

    if (!sources || sources.length === 0) {
      throw new Error('Không tìm thấy màn hình để lấy âm thanh.')
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
       * Chromium cần video track để tạo
       * desktop MediaStream theo cách này.
       *
       * Video không được gửi tới backend.
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
      if (this.platform === 'darwin') {
        throw new Error('macOS chưa cấp quyền thu âm thanh hệ thống.')
      }

      throw new Error('Nguồn màn hình không cung cấp âm thanh hệ thống.')
    }

    this.watchMediaTracks()

    await this.setupAudioPipeline()

    console.log('🖥 Đang nghe âm thanh máy tính.')
  }

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
   * Pipeline System Audio:
   *
   * MediaStream
   * → Processor
   * → Resample 16 kHz
   * → PCM16
   * → WebSocket
   *
   * Pipeline Microphone:
   *
   * MediaStream
   * → High-pass 100 Hz
   * → Low-pass 7 kHz
   * → Compressor
   * → Noise gate
   * → Resample 16 kHz
   * → PCM16
   * → WebSocket
   */
  async setupAudioPipeline() {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext

    if (!AudioContextClass) {
      throw new Error('Thiết bị không hỗ trợ AudioContext.')
    }

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

    this.processor = this.audioContext.createScriptProcessor(2048, 1, 1)

    /*
     * Chỉ áp dụng bộ lọc cho microphone.
     * System Audio đang hoạt động tốt nên giữ nguyên.
     */
    if (this.sourceType === 'microphone') {
      this.createMicrophoneFilters()

      this.source.connect(this.highPassFilter)

      this.highPassFilter.connect(this.lowPassFilter)

      this.lowPassFilter.connect(this.compressor)

      this.compressor.connect(this.processor)
    } else {
      this.source.connect(this.processor)
    }

    this.processor.onaudioprocess = (event) => {
      if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
        return
      }

      const originalInput = event.inputBuffer.getChannelData(0)

      const inputSampleRate = event.inputBuffer.sampleRate || this.audioContext.sampleRate

      let processedInput = originalInput

      /*
       * Với microphone:
       * tiếng nền sẽ được thay bằng dữ liệu 0.
       *
       * Dữ liệu 0 vẫn được gửi cho backend
       * để backend phát hiện cuối câu.
       */
      if (this.sourceType === 'microphone') {
        processedInput = this.applyMicrophoneNoiseGate(originalInput, inputSampleRate)
      }

      const samples16Khz = this.resampleAudio(processedInput, inputSampleRate, TARGET_SAMPLE_RATE)

      const pcm16 = this.convertFloat32ToPcm16(samples16Khz)

      if (pcm16.length > 0 && this.socket.readyState === WebSocket.OPEN) {
        this.socket.send(pcm16.buffer)
      }
    }

    /*
     * ScriptProcessor phải nối với destination
     * thì callback mới chạy liên tục.
     *
     * Gain bằng 0 nên không phát lại âm thanh,
     * tránh tiếng vọng.
     */
    this.gainNode = this.audioContext.createGain()

    this.gainNode.gain.value = 0

    this.processor.connect(this.gainNode)

    this.gainNode.connect(this.audioContext.destination)

    console.log(`🎧 AudioContext: ${this.audioContext.sampleRate} Hz`)
  }

  /**
   * Tạo bộ lọc dành riêng cho microphone.
   */
  createMicrophoneFilters() {
    /*
     * Lọc tiếng ù thấp như:
     * - tiếng rung bàn
     * - tiếng quạt
     * - tiếng điều hòa
     * - tiếng chạm vào microphone
     */
    this.highPassFilter = this.audioContext.createBiquadFilter()

    this.highPassFilter.type = 'highpass'

    this.highPassFilter.frequency.value = 100

    this.highPassFilter.Q.value = 0.707

    /*
     * Lọc bớt tiếng rít và nhiễu cao.
     *
     * Audio gửi sang ASR là 16 kHz,
     * nên tần số hữu ích tối đa gần 8 kHz.
     */
    this.lowPassFilter = this.audioContext.createBiquadFilter()

    this.lowPassFilter.type = 'lowpass'

    this.lowPassFilter.frequency.value = 7000

    this.lowPassFilter.Q.value = 0.707

    /*
     * Giảm chênh lệch giữa đoạn quá to
     * và đoạn nói bình thường.
     *
     * Compressor không dùng để tự khuếch đại
     * tiếng nền như autoGainControl.
     */
    this.compressor = this.audioContext.createDynamicsCompressor()

    this.compressor.threshold.value = -22

    this.compressor.knee.value = 18

    this.compressor.ratio.value = 3

    this.compressor.attack.value = 0.005

    this.compressor.release.value = 0.25
  }

  resetMicrophoneGate() {
    this.microphoneNoiseFloor = 0.003

    this.microphoneGateOpen = false

    this.microphoneGateHoldRemaining = 0
  }

  /**
   * Noise gate thích nghi với tiếng ồn trong phòng.
   *
   * Tiếng động rất ngắn có thể lọt qua một chunk,
   * nhưng backend còn kiểm tra thời lượng liên tục
   * nên sẽ không gửi ngay vào model.
   */
  applyMicrophoneNoiseGate(inputData, sampleRate) {
    if (!inputData || inputData.length === 0) {
      return new Float32Array(0)
    }

    let sumSquares = 0

    for (let index = 0; index < inputData.length; index += 1) {
      const sample = inputData[index]

      sumSquares += sample * sample
    }

    const rms = Math.sqrt(sumSquares / inputData.length)

    const chunkDuration = inputData.length / sampleRate

    /*
     * Ngưỡng mở gate tự điều chỉnh theo độ ồn.
     *
     * Không thấp hơn 0.007 để tránh quá nhạy.
     * Không cao hơn 0.025 để tránh mất giọng nhỏ.
     */
    const openThreshold = Math.min(0.025, Math.max(0.007, this.microphoneNoiseFloor * 3.2))

    /*
     * Ngưỡng đóng thấp hơn ngưỡng mở
     * để gate không bật/tắt liên tục giữa một từ.
     */
    const closeThreshold = openThreshold * 0.62

    if (this.microphoneGateOpen) {
      if (rms >= closeThreshold) {
        this.microphoneGateHoldRemaining = this.microphoneGateHoldTime
      } else {
        this.microphoneGateHoldRemaining = Math.max(
          0,
          this.microphoneGateHoldRemaining - chunkDuration
        )

        if (this.microphoneGateHoldRemaining <= 0) {
          this.microphoneGateOpen = false
        }
      }
    } else if (rms >= openThreshold) {
      this.microphoneGateOpen = true

      this.microphoneGateHoldRemaining = this.microphoneGateHoldTime
    } else {
      /*
       * Chỉ học noise floor khi gate đang đóng.
       *
       * Cập nhật chậm để một tiếng động bất ngờ
       * không làm ngưỡng tăng quá cao.
       */
      const limitedRms = Math.min(rms, 0.02)

      this.microphoneNoiseFloor = this.microphoneNoiseFloor * 0.97 + limitedRms * 0.03
    }

    if (!this.microphoneGateOpen) {
      /*
       * Không bỏ chunk.
       * Gửi một chunk im lặng cùng kích thước.
       */
      return new Float32Array(inputData.length)
    }

    return inputData
  }

  resampleAudio(inputData, inputSampleRate, outputSampleRate) {
    if (!inputData || inputData.length === 0) {
      return new Float32Array(0)
    }

    if (inputSampleRate === outputSampleRate) {
      return new Float32Array(inputData)
    }

    const ratio = inputSampleRate / outputSampleRate

    const outputLength = Math.max(1, Math.round(inputData.length / ratio))

    const outputData = new Float32Array(outputLength)

    for (let outputIndex = 0; outputIndex < outputLength; outputIndex += 1) {
      const startIndex = Math.floor(outputIndex * ratio)

      const endIndex = Math.min(inputData.length, Math.floor((outputIndex + 1) * ratio))

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

  convertFloat32ToPcm16(inputData) {
    const pcm16 = new Int16Array(inputData.length)

    for (let index = 0; index < inputData.length; index += 1) {
      const sample = Math.max(-1, Math.min(1, inputData[index]))

      pcm16[index] = sample < 0 ? Math.round(sample * 0x8000) : Math.round(sample * 0x7fff)
    }

    return pcm16
  }

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

    if (this.highPassFilter) {
      try {
        this.highPassFilter.disconnect()
      } catch (error) {
        console.warn('Không thể ngắt high-pass filter:', error)
      }

      this.highPassFilter = null
    }

    if (this.lowPassFilter) {
      try {
        this.lowPassFilter.disconnect()
      } catch (error) {
        console.warn('Không thể ngắt low-pass filter:', error)
      }

      this.lowPassFilter = null
    }

    if (this.compressor) {
      try {
        this.compressor.disconnect()
      } catch (error) {
        console.warn('Không thể ngắt compressor:', error)
      }

      this.compressor = null
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

    this.resetMicrophoneGate()

    console.log('⏹ Đã dừng AudioStreamer.')
  }
}
