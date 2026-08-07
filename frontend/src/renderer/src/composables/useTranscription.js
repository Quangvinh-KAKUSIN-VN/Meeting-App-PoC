import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'

import { AudioStreamer } from '../audioStreamer'

import { LANGUAGE_DIRECTIONS } from '../constants/appearance'

/*
 * Chỉ dùng khi IPC 'backend:get-endpoint' không khả dụng
 * (chạy renderer ngoài Electron, hoặc preload chưa expose).
 *
 * Giá trị thật lấy từ BACKEND_PORT trong electron/main/index.js.
 */
const FALLBACK_BACKEND_PORT = 8765

const MAX_VISIBLE_LINES = 30

/**
 * translationDirection: ref<'ja-vi' | 'vi-ja'> lấy từ
 * useAppearanceSettings(), truyền vào để biết nên gọi
 * endpoint nào và ghi chiều dịch vào lịch sử.
 */
export function useTranscription(translationDirection) {
  const audioSource = ref('system')
  const isRecording = ref(false)
  const isStarting = ref(false)

  const transcripts = ref([])
  const sessionHistory = ref([])
  const subtitleBoxRef = ref(null)

  let streamer = null
  let transcriptId = 0
  let historyId = 0
  let lastRawTranscript = ''

  /*
   * Backend đánh số msg_id lại từ 1 mỗi khi có kết nối WebSocket mới.
   * Nhân thêm sessionKey để dòng của phiên mới không ghi đè dòng phiên cũ.
   */
  let sessionKey = 0

  /*
   * Dòng đã bị cắt khỏi màn hình do vượt MAX_VISIBLE_LINES.
   * Nếu backend gửi bản cập nhật muộn cho một dòng đã bị cắt, bỏ qua —
   * không thì nó lại được push xuống cuối và thành dòng trùng.
   */
  let retiredKeys = new Set()

  const hasHistory = computed(() => {
    return sessionHistory.value.length > 0
  })

  /*
   * BUG-012: khi đang chạy thì không cho đổi nguồn âm thanh,
   * vì hai luồng sẽ cùng được xử lý.
   * UI dùng cờ này để disable các card chọn nguồn.
   */
  const canChangeSettings = computed(() => {
    return !isRecording.value && !isStarting.value
  })

  const scrollToLatestSubtitle = async () => {
    await nextTick()

    if (!subtitleBoxRef.value) {
      return
    }

    subtitleBoxRef.value.scrollTop = subtitleBoxRef.value.scrollHeight
  }

  /**
   * Lấy URL WebSocket từ main process.
   *
   * Cổng do BACKEND_PORT trong electron/main/index.js quyết định và được
   * truyền xuống Python qua biến môi trường KATOBA_PORT. Nhờ vậy đổi cổng
   * chỉ phải sửa một chỗ duy nhất.
   */
  const resolveWebSocketUrl = async (wsPath) => {
    try {
      const endpoint = await window.api?.getBackendEndpoint?.()

      if (endpoint) {
        const url = wsPath === 'ja' ? endpoint.wsJa : endpoint.wsVi

        if (url) {
          return url
        }
      }
    } catch (error) {
      console.warn('Không lấy được endpoint từ main process:', error)
    }

    return `ws://127.0.0.1:${FALLBACK_BACKEND_PORT}/ws/audio/${wsPath}`
  }

  /**
   * Giao thức hiện tại: { id, src, dst, final }
   *
   *   id    — cùng id nghĩa là CẬP NHẬT dòng cũ, không phải dòng mới.
   *           SentenceBuffer ở backend gộp các mẩu VAD chưa thành câu rồi
   *           dịch lại toàn bộ, nên một câu nói sinh ra nhiều message
   *           cùng id với nội dung ngày càng đầy đủ.
   *   final — false nghĩa là còn đang nghe tiếp, nên render mờ/nghiêng.
   *
   * Vẫn chấp nhận text thuần và { src, dst } của giao thức cũ.
   */
  const parseIncomingMessage = (raw) => {
    const trimmedRaw = raw.trim()

    const asPlainText = {
      id: null,
      src: '',
      dst: trimmedRaw,
      final: true
    }

    if (!trimmedRaw.startsWith('{')) {
      return asPlainText
    }

    try {
      const parsed = JSON.parse(trimmedRaw)

      if (!parsed || typeof parsed !== 'object') {
        return asPlainText
      }

      const dst =
        typeof parsed.dst === 'string'
          ? parsed.dst
          : typeof parsed.text === 'string'
            ? parsed.text
            : trimmedRaw

      return {
        id: Number.isFinite(parsed.id) ? parsed.id : null,
        src: typeof parsed.src === 'string' ? parsed.src.trim() : '',
        dst,
        final: typeof parsed.final === 'boolean' ? parsed.final : true
      }
    } catch (error) {
      return asPlainText
    }
  }

  const addTranscript = async (receivedText) => {
    if (typeof receivedText !== 'string') {
      return
    }

    const { id: backendId, src: sourceText, dst, final } = parseIncomingMessage(receivedText)

    const translatedText = dst.trim()

    if (!translatedText) {
      return
    }

    /*
     * Giao thức cũ không có id -> mỗi message là một dòng mới,
     * nên vẫn cần lọc trùng liên tiếp như trước.
     * Giao thức mới có backend lọc trùng (Deduper) rồi.
     */
    if (backendId === null) {
      const dedupeKey = `${sourceText}|${translatedText}`

      if (dedupeKey === lastRawTranscript) {
        return
      }

      lastRawTranscript = dedupeKey
    }

    const lineKey =
      backendId === null ? `raw:${sessionKey}:${transcriptId + 1}` : `s${sessionKey}:${backendId}`

    if (retiredKeys.has(lineKey)) {
      return
    }

    const existingLine = transcripts.value.find((item) => item.key === lineKey)

    if (existingLine) {
      existingLine.src = sourceText
      existingLine.text = translatedText
      existingLine.final = final
    } else {
      transcriptId += 1

      transcripts.value.push({
        id: transcriptId,
        key: lineKey,
        src: sourceText,
        text: translatedText,
        final,
        type: 'translation'
      })
    }

    /*
     * Lịch sử xuất file CHỈ ghi câu đã chốt.
     *
     * Nếu ghi cả câu tạm thời thì biên bản sẽ đầy những mẩu dở dang
     * như "Phần này trước khi giao" nằm ngay trên câu hoàn chỉnh của nó.
     */
    if (final) {
      const existingEntry = sessionHistory.value.find((entry) => entry.key === lineKey)

      if (existingEntry) {
        existingEntry.src = sourceText
        existingEntry.dst = translatedText
      } else {
        historyId += 1

        sessionHistory.value.push({
          id: historyId,
          key: lineKey,
          timestamp: new Date(),
          direction: translationDirection.value,
          src: sourceText,
          dst: translatedText
        })
      }
    }

    if (transcripts.value.length > MAX_VISIBLE_LINES) {
      const removed = transcripts.value.splice(0, transcripts.value.length - MAX_VISIBLE_LINES)

      for (const line of removed) {
        retiredKeys.add(line.key)
      }

      // Giữ Set khỏi phình vô hạn trong phiên họp dài
      if (retiredKeys.size > 500) {
        retiredKeys = new Set([...retiredKeys].slice(-200))
      }
    }

    await scrollToLatestSubtitle()
  }

  const addErrorMessage = (message) => {
    transcriptId += 1

    transcripts.value.push({
      id: transcriptId,
      key: `error:${sessionKey}:${transcriptId}`,
      text: message,
      final: true,
      type: 'error'
    })
  }

  /*
   * BUG-012: chặn đổi nguồn âm thanh khi đang chạy.
   * Trả false để UI biết thao tác bị từ chối.
   */
  const setAudioSource = (nextSource) => {
    if (!canChangeSettings.value) {
      return false
    }

    audioSource.value = nextSource

    return true
  }

  const startRecording = async () => {
    if (isRecording.value || isStarting.value) {
      return
    }

    transcripts.value = []
    lastRawTranscript = ''
    transcriptId = 0
    retiredKeys = new Set()
    sessionKey += 1

    isStarting.value = true

    try {
      const wsPath = LANGUAGE_DIRECTIONS[translationDirection.value].wsPath

      const websocketUrl = await resolveWebSocketUrl(wsPath)

      streamer = new AudioStreamer(websocketUrl, addTranscript)

      await streamer.start(audioSource.value)

      isRecording.value = true
    } catch (error) {
      console.error('❌ Không thể bắt đầu dịch:', error)

      if (streamer) {
        try {
          await streamer.stop()
        } catch (stopError) {
          console.error('Không thể dọn AudioStreamer:', stopError)
        }
      }

      streamer = null
      isRecording.value = false

      const sourceLabel = audioSource.value === 'microphone' ? 'microphone' : 'âm thanh máy tính'

      addErrorMessage(`Không thể mở ${sourceLabel}: ${error?.message || 'Lỗi không xác định'}`)
    } finally {
      isStarting.value = false
    }
  }

  const stopRecording = async () => {
    isRecording.value = false
    isStarting.value = false

    if (streamer) {
      try {
        await streamer.stop()
      } catch (error) {
        console.error('❌ Lỗi khi dừng:', error)
      }
    }

    streamer = null

    /*
     * Câu đang dở sẽ không bao giờ nhận được bản final nữa
     * -> chốt lại để nó không kẹt ở trạng thái mờ vĩnh viễn.
     */
    for (const line of transcripts.value) {
      line.final = true
    }
  }

  /*
   * BUG-011: đổi chiều dịch giữa chừng làm phụ đề hai chiều lẫn vào nhau,
   * vì phiên phía backend không được tạo lại (mỗi chiều là một endpoint
   * WebSocket khác nhau: /ws/audio/ja và /ws/audio/vi).
   */
  watch(translationDirection, async (nextDirection, previousDirection) => {
    if (nextDirection === previousDirection) {
      return
    }

    if (!isRecording.value && !isStarting.value) {
      return
    }

    console.log(`🔄 Đổi chiều ${previousDirection} → ${nextDirection}, tạo lại phiên.`)

    await stopRecording()

    transcripts.value = []
    retiredKeys = new Set()

    await startRecording()
  })

  /*
   * BUG-026: backend chết thì renderer phải biết,
   * không thì AudioStreamer cứ thử reconnect mù rồi bỏ cuộc trong im lặng.
   */
  if (typeof window !== 'undefined' && window.api?.onBackendDown) {
    window.api.onBackendDown(async ({ code }) => {
      console.error(`❌ Backend đã dừng (code=${code})`)

      if (isRecording.value || isStarting.value) {
        await stopRecording()
      }

      addErrorMessage(
        `Backend đã dừng hoạt động (code=${code}). Vui lòng khởi động lại ứng dụng.`
      )
    })
  }

  const clearTranscripts = () => {
    transcripts.value = []
    lastRawTranscript = ''
    retiredKeys = new Set()
  }

  const formatEntryTimestamp = (date) => {
    const pad = (value) => String(value).padStart(2, '0')

    return `${pad(date.getHours())}:` + `${pad(date.getMinutes())}:` + `${pad(date.getSeconds())}`
  }

  const formatExportTimestamp = (date) => {
    const pad = (value) => String(value).padStart(2, '0')

    return (
      `${date.getFullYear()}-` +
      `${pad(date.getMonth() + 1)}-` +
      `${pad(date.getDate())} ` +
      `${pad(date.getHours())}:` +
      `${pad(date.getMinutes())}`
    )
  }

  const exportHistory = () => {
    if (sessionHistory.value.length === 0) {
      return
    }

    const now = new Date()

    const lines = [
      'BIÊN BẢN PHIÊN DỊCH CUỘC HỌP',
      `Xuất lúc: ${formatExportTimestamp(now)}`,
      `Số câu đã dịch: ${sessionHistory.value.length}`,
      '',
      '='.repeat(50),
      ''
    ]

    for (const entry of sessionHistory.value) {
      const info = LANGUAGE_DIRECTIONS[entry.direction] || LANGUAGE_DIRECTIONS['ja-vi']

      lines.push(`[${formatEntryTimestamp(entry.timestamp)}]`)

      if (entry.src) {
        lines.push(`${info.sourceCode}: ${entry.src}`)
      }

      lines.push(`${info.targetCode}: ${entry.dst}`)

      lines.push('')
    }

    /*
     * BOM ở đầu file (BUG-013).
     *
     * Không có BOM, Excel và Notepad đời cũ trên Windows đọc UTF-8 thành
     * Shift-JIS hoặc CP1258 -> hỏng cả chữ Nhật lẫn chữ Việt có dấu.
     * Ba byte này rẻ hơn nhiều so với việc giải thích cho người dùng.
     */
    const fileContent = '\uFEFF' + lines.join('\r\n')

    const blob = new Blob([fileContent], {
      type: 'text/plain;charset=utf-8'
    })

    const objectUrl = URL.createObjectURL(blob)

    const pad = (value) => String(value).padStart(2, '0')

    const fileName =
      `bien-ban-hop-${now.getFullYear()}` +
      `${pad(now.getMonth() + 1)}` +
      `${pad(now.getDate())}-` +
      `${pad(now.getHours())}` +
      `${pad(now.getMinutes())}.txt`

    const downloadLink = document.createElement('a')

    downloadLink.href = objectUrl
    downloadLink.download = fileName

    document.body.appendChild(downloadLink)
    downloadLink.click()
    document.body.removeChild(downloadLink)

    URL.revokeObjectURL(objectUrl)
  }

  onBeforeUnmount(async () => {
    if (streamer) {
      await streamer.stop()
      streamer = null
    }
  })

  return {
    audioSource,
    isRecording,
    isStarting,
    canChangeSettings,
    transcripts,
    sessionHistory,
    hasHistory,
    subtitleBoxRef,
    setAudioSource,
    startRecording,
    stopRecording,
    clearTranscripts,
    exportHistory
  }
}
