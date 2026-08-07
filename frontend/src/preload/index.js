import { contextBridge, ipcRenderer } from 'electron'

import { electronAPI } from '@electron-toolkit/preload'

/**
 * Bọc ipcRenderer.on và trả về hàm huỷ đăng ký.
 *
 * Bản cũ chỉ có removeAllListeners — gọi onMaximizedChange hai lần là
 * callback chạy hai lần, và muốn gỡ một cái thì phải gỡ sạch cả đám.
 * Với composable Vue được tạo/huỷ nhiều lần thì đó là rò rỉ listener.
 */
const subscribe = (channel, callback, transform) => {
  if (typeof callback !== 'function') {
    return () => {}
  }

  const handler = (_event, payload) => {
    callback(transform ? transform(payload) : payload)
  }

  ipcRenderer.on(channel, handler)

  return () => {
    ipcRenderer.removeListener(channel, handler)
  }
}

const api = {
  /*
   * win32  = Windows
   * darwin = macOS
   * linux  = Linux
   */
  platform: process.platform,

  getSources: (options) => {
    return ipcRenderer.invoke('get-sources', options)
  },

  /*
   * ---- BACKEND ----
   *
   * Cổng backend do BACKEND_PORT trong electron/main/index.js quyết định,
   * và được truyền xuống tiến trình Python qua biến môi trường KATOBA_PORT.
   *
   * Renderer PHẢI lấy URL qua đây, không viết cứng ws://127.0.0.1:8765.
   * Nhờ vậy đổi cổng chỉ phải sửa đúng một chỗ.
   */

  getBackendEndpoint: () => {
    return ipcRenderer.invoke('backend:get-endpoint')
  },

  isBackendRunning: () => {
    return ipcRenderer.invoke('backend:is-running')
  },

  /**
   * Backend crash giữa phiên.
   *
   * Không có tín hiệu này, AudioStreamer cứ thử kết nối lại rồi bỏ cuộc
   * trong im lặng, người dùng không hiểu vì sao phụ đề đứng — chính là
   * triệu chứng của BUG-026.
   *
   * Trả về hàm huỷ đăng ký:
   *   const off = window.api.onBackendDown(handler)
   *   onBeforeUnmount(off)
   */
  onBackendDown: (callback) => {
    return subscribe('backend:down', callback, (payload) => ({
      code: payload?.code ?? null,
      signal: payload?.signal ?? null
    }))
  },

  removeBackendDownListeners: () => {
    ipcRenderer.removeAllListeners('backend:down')
  },

  windowControls: {
    minimize: () => {
      ipcRenderer.send('window:minimize')
    },

    toggleMaximize: () => {
      return ipcRenderer.invoke('window:toggle-maximize')
    },

    close: () => {
      ipcRenderer.send('window:close')
    },

    getState: () => {
      return ipcRenderer.invoke('window:get-state')
    },

    setAlwaysOnTop: (enabled) => {
      return ipcRenderer.invoke('window:set-always-on-top', Boolean(enabled))
    },

    startResize: (edge) => {
      ipcRenderer.send('window:start-resize', edge)
    },

    stopResize: () => {
      ipcRenderer.send('window:stop-resize')
    },

    /*
     * Giờ trả về hàm huỷ đăng ký. Vẫn dùng được kiểu cũ
     * (bỏ qua giá trị trả về) nên không phá code hiện có.
     */
    onMaximizedChange: (callback) => {
      return subscribe('window:maximized-changed', callback, (value) => Boolean(value))
    },

    removeMaximizedChangeListeners: () => {
      ipcRenderer.removeAllListeners('window:maximized-changed')
    }
  }
}

if (process.contextIsolated) {
  try {
    contextBridge.exposeInMainWorld('electron', electronAPI)

    contextBridge.exposeInMainWorld('api', api)
  } catch (error) {
    console.error('Không thể khởi tạo preload:', error)
  }
} else {
  window.electron = electronAPI
  window.api = api
}
