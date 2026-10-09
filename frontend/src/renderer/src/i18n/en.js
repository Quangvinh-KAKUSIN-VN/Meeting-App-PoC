// Cùng cấu trúc với vi.js — thêm key mới thì thêm ở cả hai file
export default {
  status: {
    starting: 'Connecting',
    recording: 'Translating',
    ready: 'Ready'
  },

  languages: {
    ja: 'Japanese',
    vi: 'Vietnamese',
    en: 'English'
  },

  directions: {
    'ja-vi': {
      listening: 'Listening for Japanese',
      hint: 'Choose an audio source, then start interpreting Japanese → Vietnamese.'
    },
    'vi-ja': {
      listening: 'Listening for Vietnamese',
      hint: 'Choose an audio source, then start interpreting Vietnamese → Japanese.'
    },
    'en-vi': {
      listening: 'Listening for English',
      hint: 'Choose an audio source, then start interpreting English → Vietnamese.'
    },
    'vi-en': {
      listening: 'Listening for Vietnamese',
      hint: 'Choose an audio source, then start interpreting Vietnamese → English.'
    }
  },

  topBar: {
    directionLocked: 'Stop interpreting to change direction',
    switchDirection: 'Switch translation direction',
    switchDirectionAria: 'Switch translation direction, currently {source} to {target}',
    showControls: 'Show controls',
    focusMode: 'Show subtitles only',
    unlockWindow: 'Unlock window',
    lockWindow: 'Lock position and size',
    appearance: 'Customize appearance',
    exportHistory: 'Export meeting history',
    nothingToExport: 'Nothing to export yet',
    clearSubtitles: 'Clear subtitles',
    minimize: 'Minimize',
    minimizeAria: 'Minimize window',
    restore: 'Restore size',
    maximize: 'Maximize',
    maximizeAria: 'Maximize window',
    close: 'Close',
    closeAria: 'Close window'
  },

  controls: {
    systemAudio: 'System audio',
    systemAudioHint: 'Zoom, Meet, YouTube',
    microphone: 'Microphone',
    microphoneHint: 'Live speaker or loudspeaker',
    start: 'Start interpreting',
    starting: 'Starting...',
    stop: 'Stop interpreting'
  },

  placeholder: {
    connectingTitle: 'Connecting to AI',
    idleTitle: 'Subtitles will appear here',
    connectingText: 'Preparing the audio source and connecting to the backend.',
    microphoneText: 'Keep the microphone close to the speaker or loudspeaker.',
    systemText: 'Listening to system audio on {platform}.'
  },

  footer: {
    resizeHint: 'Drag an edge or corner to resize'
  },

  platform: {
    unknown: 'Unknown OS'
  },

  appearance: {
    title: 'Subtitle display',
    subtitle: 'Changes are saved automatically',
    close: 'Close settings panel',
    uiLanguage: 'Interface language',
    textColor: 'Text color',
    customColor: 'Choose another color',
    fontSize: 'Font size',
    opacity: 'Background opacity',
    outline: 'Text outline',
    align: 'Subtitle alignment',
    alignLeft: 'Left',
    alignCenter: 'Center',
    alignRight: 'Right',
    alwaysOnTop: 'Always on top',
    alwaysOnTopHint: 'Keep subtitles above Zoom or Meet',
    reset: 'Restore default appearance'
  },

  colors: {
    white: 'White',
    warmYellow: 'Warm yellow',
    cyan: 'Cyan',
    green: 'Green',
    orange: 'Orange',
    pink: 'Pink'
  },

  errors: {
    openSourceFailed: 'Could not open {source}: {reason}',
    sourceSystem: 'system audio',
    sourceMicrophone: 'microphone',
    unknown: 'Unknown error',
    backendDown: 'The backend has stopped (code={code}). Please restart the app.'
  },

  streamerErrors: {
    invalidSource: 'Invalid audio source: {source}',
    backendTimeout: 'Could not connect to the backend within 5 seconds.',
    backendUnreachable: 'Could not connect to the backend.',
    socketClosedEarly: 'The WebSocket closed before the connection was established.',
    micUnsupported: 'This device does not support microphone input.',
    micNotFound: 'No microphone found.',
    sourcesApiMissing: 'The screen source API is unavailable.',
    screenNotFound: 'No screen found to capture audio from.',
    macPermission: 'macOS has not granted permission to capture system audio.',
    noSystemAudio: 'The screen source does not provide system audio.',
    audioContextUnsupported: 'This device does not support AudioContext.'
  },

  export: {
    title: 'MEETING INTERPRETATION TRANSCRIPT',
    exportedAt: 'Exported at: {time}',
    sentenceCount: 'Sentences translated: {count}',
    fileNamePrefix: 'meeting-transcript'
  }
}
