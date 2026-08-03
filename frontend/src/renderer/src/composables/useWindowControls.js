import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

export function useWindowControls(options = {}) {
  const { onBeforeClose } = options

  const platform = ref(window.api?.platform || 'unknown')

  const isMaximized = ref(false)
  const keepOnTop = ref(true)
  const isResizing = ref(false)

  const isMac = computed(() => platform.value === 'darwin')

  const platformLabel = computed(() => {
    switch (platform.value) {
      case 'win32':
        return 'Windows'

      case 'darwin':
        return 'macOS'

      case 'linux':
        return 'Linux'

      default:
        return 'Unknown OS'
    }
  })

  const platformClass = computed(() => {
    switch (platform.value) {
      case 'win32':
        return 'platform-windows'

      case 'darwin':
        return 'platform-mac'

      case 'linux':
        return 'platform-linux'

      default:
        return 'platform-unknown'
    }
  })

  const setAlwaysOnTop = async (enabled) => {
    try {
      const result = await window.api?.windowControls?.setAlwaysOnTop(enabled)

      keepOnTop.value = typeof result === 'boolean' ? result : Boolean(enabled)
    } catch (error) {
      console.error('Không thể đổi chế độ luôn nổi:', error)
    }
  }

  const minimizeWindow = () => {
    window.api?.windowControls?.minimize()
  }

  const stopWindowResize = () => {
    if (!isResizing.value) {
      return
    }

    isResizing.value = false

    window.api?.windowControls?.stopResize()
  }

  const startWindowResize = (edge) => {
    /*
     * Template chỉ render các tay cầm resize khi
     * !isLocked && !isMaximized, nên chỉ cần chặn
     * thêm isMaximized ở đây cho chắc chắn.
     */
    if (isMaximized.value) {
      return
    }

    isResizing.value = true

    window.api?.windowControls?.startResize(edge)
  }

  const toggleMaximizeWindow = async () => {
    try {
      stopWindowResize()

      const newState = await window.api?.windowControls?.toggleMaximize()

      if (typeof newState === 'boolean') {
        isMaximized.value = newState
      }
    } catch (error) {
      console.error('Không thể thay đổi kích thước cửa sổ:', error)
    }
  }

  const closeWindow = async () => {
    stopWindowResize()

    if (onBeforeClose) {
      await onBeforeClose()
    }

    window.api?.windowControls?.close()
  }

  onMounted(async () => {
    window.addEventListener('mouseup', stopWindowResize)

    window.addEventListener('blur', stopWindowResize)

    try {
      const windowState = await window.api?.windowControls?.getState()

      if (windowState) {
        platform.value = windowState.platform

        isMaximized.value = Boolean(windowState.isMaximized)

        keepOnTop.value = Boolean(windowState.isAlwaysOnTop)
      }

      window.api?.windowControls?.onMaximizedChange((newState) => {
        isMaximized.value = Boolean(newState)
      })
    } catch (error) {
      console.error('Không thể đọc trạng thái cửa sổ:', error)
    }
  })

  onBeforeUnmount(() => {
    stopWindowResize()

    window.removeEventListener('mouseup', stopWindowResize)

    window.removeEventListener('blur', stopWindowResize)

    window.api?.windowControls?.removeMaximizedChangeListeners()
  })

  return {
    platform,
    isMaximized,
    keepOnTop,
    isResizing,
    isMac,
    platformLabel,
    platformClass,
    setAlwaysOnTop,
    minimizeWindow,
    toggleMaximizeWindow,
    closeWindow,
    startWindowResize,
    stopWindowResize
  }
}
