import { contextBridge, ipcRenderer } from 'electron'

import { electronAPI } from '@electron-toolkit/preload'

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

    onMaximizedChange: (callback) => {
      if (typeof callback !== 'function') {
        return
      }

      ipcRenderer.on('window:maximized-changed', (_event, isMaximized) => {
        callback(Boolean(isMaximized))
      })
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
