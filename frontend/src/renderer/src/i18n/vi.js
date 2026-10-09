export default {
  status: {
    starting: 'Đang kết nối',
    recording: 'Đang dịch',
    ready: 'Sẵn sàng'
  },

  // Tên hiển thị ở dòng chú thích dưới logo, ví dụ "Tiếng Nhật → Tiếng Việt"
  languages: {
    ja: 'Tiếng Nhật',
    vi: 'Tiếng Việt',
    en: 'Tiếng Anh'
  },

  // Key trùng với key của LANGUAGE_DIRECTIONS
  directions: {
    'ja-vi': {
      listening: 'Đang lắng nghe tiếng Nhật',
      hint: 'Chọn nguồn âm thanh rồi bắt đầu phiên dịch Nhật → Việt.'
    },
    'vi-ja': {
      listening: 'Đang lắng nghe tiếng Việt',
      hint: 'Chọn nguồn âm thanh rồi bắt đầu phiên dịch Việt → Nhật.'
    },
    'en-vi': {
      listening: 'Đang lắng nghe tiếng Anh',
      hint: 'Chọn nguồn âm thanh rồi bắt đầu phiên dịch Anh → Việt.'
    },
    'vi-en': {
      listening: 'Đang lắng nghe tiếng Việt',
      hint: 'Chọn nguồn âm thanh rồi bắt đầu phiên dịch Việt → Anh.'
    }
  },

  topBar: {
    directionLocked: 'Dừng phiên dịch để đổi chiều',
    switchDirection: 'Đổi chiều dịch',
    switchDirectionAria: 'Đổi chiều dịch, hiện tại {source} sang {target}',
    showControls: 'Hiện bảng điều khiển',
    focusMode: 'Chỉ hiển thị phụ đề',
    unlockWindow: 'Mở khóa cửa sổ',
    lockWindow: 'Khóa vị trí và kích thước',
    appearance: 'Tùy chỉnh giao diện',
    exportHistory: 'Xuất file lịch sử cuộc họp',
    nothingToExport: 'Chưa có nội dung để xuất',
    clearSubtitles: 'Xóa phụ đề',
    minimize: 'Thu nhỏ',
    minimizeAria: 'Thu nhỏ cửa sổ',
    restore: 'Khôi phục kích thước',
    maximize: 'Phóng to',
    maximizeAria: 'Phóng to cửa sổ',
    close: 'Đóng',
    closeAria: 'Đóng cửa sổ'
  },

  controls: {
    systemAudio: 'Âm thanh máy tính',
    systemAudioHint: 'Zoom, Meet, YouTube',
    microphone: 'Microphone',
    microphoneHint: 'Người nói hoặc loa ngoài',
    start: 'Bắt đầu phiên dịch',
    starting: 'Đang khởi động...',
    stop: 'Dừng phiên dịch'
  },

  placeholder: {
    connectingTitle: 'Đang kết nối với AI',
    idleTitle: 'Phụ đề sẽ xuất hiện tại đây',
    connectingText: 'Đang chuẩn bị nguồn âm thanh và kết nối backend.',
    microphoneText: 'Hãy để microphone gần người nói hoặc loa ngoài.',
    systemText: 'Đang nghe âm thanh máy tính trên {platform}.'
  },

  footer: {
    resizeHint: 'Kéo cạnh hoặc góc để đổi kích thước'
  },

  platform: {
    unknown: 'Không rõ hệ điều hành'
  },

  appearance: {
    title: 'Hiển thị phụ đề',
    subtitle: 'Tùy chỉnh và tự động lưu',
    close: 'Đóng bảng tùy chỉnh',
    uiLanguage: 'Ngôn ngữ giao diện',
    textColor: 'Màu chữ',
    customColor: 'Chọn màu khác',
    fontSize: 'Cỡ chữ',
    opacity: 'Độ trong suốt nền',
    outline: 'Viền chữ',
    align: 'Căn chỉnh phụ đề',
    alignLeft: 'Trái',
    alignCenter: 'Giữa',
    alignRight: 'Phải',
    alwaysOnTop: 'Luôn nổi trên cùng',
    alwaysOnTopHint: 'Giữ phụ đề phía trên Zoom hoặc Meet',
    reset: 'Khôi phục giao diện mặc định'
  },

  // Key trùng với colorPresets[].key trong constants/appearance.js
  colors: {
    white: 'Trắng',
    warmYellow: 'Vàng ấm',
    cyan: 'Xanh cyan',
    green: 'Xanh lá',
    orange: 'Cam',
    pink: 'Hồng'
  },

  errors: {
    openSourceFailed: 'Không thể mở {source}: {reason}',
    sourceSystem: 'âm thanh máy tính',
    sourceMicrophone: 'microphone',
    unknown: 'Lỗi không xác định',
    backendDown: 'Backend đã dừng hoạt động (code={code}). Vui lòng khởi động lại ứng dụng.'
  },

  // Lỗi do AudioStreamer ném ra, hiện trong phần "{reason}" ở trên
  streamerErrors: {
    invalidSource: 'Nguồn âm thanh không hợp lệ: {source}',
    backendTimeout: 'Không thể kết nối backend trong vòng 5 giây.',
    backendUnreachable: 'Không thể kết nối tới backend.',
    socketClosedEarly: 'WebSocket bị đóng trước khi kết nối.',
    micUnsupported: 'Thiết bị không hỗ trợ microphone.',
    micNotFound: 'Không tìm thấy microphone.',
    sourcesApiMissing: 'Không tìm thấy API lấy nguồn màn hình.',
    screenNotFound: 'Không tìm thấy màn hình để lấy âm thanh.',
    macPermission: 'macOS chưa cấp quyền thu âm thanh hệ thống.',
    noSystemAudio: 'Nguồn màn hình không cung cấp âm thanh hệ thống.',
    audioContextUnsupported: 'Thiết bị không hỗ trợ AudioContext.'
  },

  // File biên bản xuất ra theo ngôn ngữ giao diện lúc bấm xuất
  export: {
    title: 'BIÊN BẢN PHIÊN DỊCH CUỘC HỌP',
    exportedAt: 'Xuất lúc: {time}',
    sentenceCount: 'Số câu đã dịch: {count}',
    fileNamePrefix: 'bien-ban-hop'
  }
}
