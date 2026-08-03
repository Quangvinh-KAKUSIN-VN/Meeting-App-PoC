import {
  app,
  shell,
  BrowserWindow,
  ipcMain,
  desktopCapturer,
  session,
  systemPreferences,
  screen
} from 'electron'

import { existsSync, readFileSync, writeFileSync } from 'node:fs'
import { join } from 'path'
import { electronApp, optimizer, is } from '@electron-toolkit/utils'

import icon from '../../resources/icon.png?asset'

const PLATFORM = process.platform

const IS_WINDOWS = PLATFORM === 'win32'
const IS_MAC = PLATFORM === 'darwin'
const IS_LINUX = PLATFORM === 'linux'

const DEFAULT_WIDTH = 920
const DEFAULT_HEIGHT = 380

const MIN_WIDTH = 460
const MIN_HEIGHT = 180

const RESIZE_INTERVAL_MS = 16
const WINDOW_STATE_SAVE_DELAY_MS = 250

const VALID_RESIZE_EDGES = new Set([
  'top',
  'right',
  'bottom',
  'left',
  'top-left',
  'top-right',
  'bottom-left',
  'bottom-right'
])

let mainWindow = null

let resizeState = null
let resizeTimer = null
let saveWindowStateTimer = null

function getWindowStateFilePath() {
  return join(app.getPath('userData'), 'katoba-window-state.json')
}

function getDefaultWindowBounds() {
  const { workArea } = screen.getPrimaryDisplay()

  const width = Math.min(DEFAULT_WIDTH, workArea.width)
  const height = Math.min(DEFAULT_HEIGHT, workArea.height)

  return {
    x: Math.round(workArea.x + (workArea.width - width) / 2),
    y: Math.round(workArea.y + (workArea.height - height) / 2),
    width,
    height
  }
}

function normalizeWindowBounds(savedBounds) {
  if (
    !savedBounds ||
    !Number.isFinite(savedBounds.x) ||
    !Number.isFinite(savedBounds.y) ||
    !Number.isFinite(savedBounds.width) ||
    !Number.isFinite(savedBounds.height)
  ) {
    return getDefaultWindowBounds()
  }

  const display = screen.getDisplayMatching(savedBounds)
  const { workArea } = display

  const width = Math.min(Math.max(Math.round(savedBounds.width), MIN_WIDTH), workArea.width)

  const height = Math.min(Math.max(Math.round(savedBounds.height), MIN_HEIGHT), workArea.height)

  const maximumX = workArea.x + workArea.width - width
  const maximumY = workArea.y + workArea.height - height

  return {
    x: Math.min(Math.max(Math.round(savedBounds.x), workArea.x), maximumX),
    y: Math.min(Math.max(Math.round(savedBounds.y), workArea.y), maximumY),
    width,
    height
  }
}

function readWindowState() {
  try {
    const stateFilePath = getWindowStateFilePath()

    if (!existsSync(stateFilePath)) {
      return {
        bounds: getDefaultWindowBounds(),
        alwaysOnTop: true
      }
    }

    const storedState = JSON.parse(
      readFileSync(stateFilePath, {
        encoding: 'utf-8'
      })
    )

    return {
      bounds: normalizeWindowBounds(storedState.bounds),
      alwaysOnTop: typeof storedState.alwaysOnTop === 'boolean' ? storedState.alwaysOnTop : true
    }
  } catch (error) {
    console.warn('Không thể đọc trạng thái cửa sổ:', error)

    return {
      bounds: getDefaultWindowBounds(),
      alwaysOnTop: true
    }
  }
}

function saveWindowState(targetWindow) {
  if (!targetWindow || targetWindow.isDestroyed()) {
    return
  }

  try {
    const state = {
      bounds: targetWindow.getNormalBounds(),
      alwaysOnTop: targetWindow.isAlwaysOnTop()
    }

    writeFileSync(getWindowStateFilePath(), JSON.stringify(state, null, 2), {
      encoding: 'utf-8'
    })
  } catch (error) {
    console.warn('Không thể lưu trạng thái cửa sổ:', error)
  }
}

function scheduleWindowStateSave(targetWindow) {
  if (saveWindowStateTimer) {
    clearTimeout(saveWindowStateTimer)
  }

  saveWindowStateTimer = setTimeout(() => {
    saveWindowState(targetWindow)
    saveWindowStateTimer = null
  }, WINDOW_STATE_SAVE_DELAY_MS)
}

function getWindowFromEvent(event) {
  const targetWindow = BrowserWindow.fromWebContents(event.sender)

  if (!targetWindow || targetWindow.isDestroyed()) {
    return null
  }

  return targetWindow
}

function isMainWindowRenderer(webContents) {
  return Boolean(
    mainWindow &&
    !mainWindow.isDestroyed() &&
    webContents &&
    webContents.id === mainWindow.webContents.id
  )
}

function sendMaximizedState(targetWindow) {
  if (!targetWindow || targetWindow.isDestroyed() || targetWindow.webContents.isDestroyed()) {
    return
  }

  targetWindow.webContents.send('window:maximized-changed', targetWindow.isMaximized())
}

function setAlwaysOnTopForPlatform(targetWindow, enabled) {
  if (!targetWindow || targetWindow.isDestroyed()) {
    return false
  }

  if (!enabled) {
    targetWindow.setAlwaysOnTop(false)
    return false
  }

  if (IS_MAC) {
    targetWindow.setAlwaysOnTop(true, 'floating')

    targetWindow.setVisibleOnAllWorkspaces(true, {
      visibleOnFullScreen: true
    })
  } else if (IS_WINDOWS) {
    targetWindow.setAlwaysOnTop(true, 'screen-saver')
  } else {
    targetWindow.setAlwaysOnTop(true)
  }

  return targetWindow.isAlwaysOnTop()
}

function stopResizeLoop() {
  if (resizeTimer) {
    clearInterval(resizeTimer)
    resizeTimer = null
  }

  resizeState = null
}

function calculateResizedBounds(edge, startBounds, deltaX, deltaY, workArea) {
  let left = startBounds.x
  let top = startBounds.y
  let right = startBounds.x + startBounds.width
  let bottom = startBounds.y + startBounds.height

  const workAreaRight = workArea.x + workArea.width
  const workAreaBottom = workArea.y + workArea.height

  if (edge.includes('right')) {
    right = Math.min(Math.max(startBounds.x + MIN_WIDTH, right + deltaX), workAreaRight)
  }

  if (edge.includes('left')) {
    left = Math.max(Math.min(startBounds.x + deltaX, right - MIN_WIDTH), workArea.x)
  }

  if (edge.includes('bottom')) {
    bottom = Math.min(Math.max(startBounds.y + MIN_HEIGHT, bottom + deltaY), workAreaBottom)
  }

  if (edge.includes('top')) {
    top = Math.max(Math.min(startBounds.y + deltaY, bottom - MIN_HEIGHT), workArea.y)
  }

  return {
    x: Math.round(left),
    y: Math.round(top),
    width: Math.round(right - left),
    height: Math.round(bottom - top)
  }
}

function startResizeLoop(targetWindow, edge) {
  if (
    !targetWindow ||
    targetWindow.isDestroyed() ||
    targetWindow.isMaximized() ||
    !VALID_RESIZE_EDGES.has(edge)
  ) {
    return
  }

  stopResizeLoop()

  const startBounds = targetWindow.getBounds()
  const startCursor = screen.getCursorScreenPoint()
  const display = screen.getDisplayMatching(startBounds)

  resizeState = {
    windowId: targetWindow.id,
    edge,
    startBounds,
    startCursor,
    workArea: display.workArea
  }

  resizeTimer = setInterval(() => {
    if (!resizeState) {
      stopResizeLoop()
      return
    }

    const activeWindow = BrowserWindow.fromId(resizeState.windowId)

    if (!activeWindow || activeWindow.isDestroyed()) {
      stopResizeLoop()
      return
    }

    const currentCursor = screen.getCursorScreenPoint()

    const nextBounds = calculateResizedBounds(
      resizeState.edge,
      resizeState.startBounds,
      currentCursor.x - resizeState.startCursor.x,
      currentCursor.y - resizeState.startCursor.y,
      resizeState.workArea
    )

    activeWindow.setBounds(nextBounds)
  }, RESIZE_INTERVAL_MS)
}

/*
 * Các nút và thao tác cửa sổ:
 * — Thu nhỏ
 * □ Phóng to/khôi phục
 * × Đóng
 * Kéo cạnh/góc để thay đổi kích thước
 */
function registerWindowControlHandlers() {
  ipcMain.removeAllListeners('window:minimize')
  ipcMain.removeAllListeners('window:close')
  ipcMain.removeAllListeners('window:start-resize')
  ipcMain.removeAllListeners('window:stop-resize')

  ipcMain.removeHandler('window:toggle-maximize')
  ipcMain.removeHandler('window:get-state')
  ipcMain.removeHandler('window:set-always-on-top')

  ipcMain.on('window:minimize', (event) => {
    const targetWindow = getWindowFromEvent(event)

    targetWindow?.minimize()
  })

  ipcMain.handle('window:toggle-maximize', (event) => {
    const targetWindow = getWindowFromEvent(event)

    if (!targetWindow) {
      return false
    }

    stopResizeLoop()

    if (targetWindow.isMaximized()) {
      targetWindow.unmaximize()
    } else {
      targetWindow.maximize()
    }

    const isMaximized = targetWindow.isMaximized()

    sendMaximizedState(targetWindow)

    return isMaximized
  })

  ipcMain.on('window:close', (event) => {
    const targetWindow = getWindowFromEvent(event)

    targetWindow?.close()
  })

  ipcMain.handle('window:get-state', (event) => {
    const targetWindow = getWindowFromEvent(event)

    return {
      platform: PLATFORM,
      isWindows: IS_WINDOWS,
      isMac: IS_MAC,
      isLinux: IS_LINUX,
      isMaximized: targetWindow?.isMaximized() ?? false,
      isAlwaysOnTop: targetWindow?.isAlwaysOnTop() ?? true,
      bounds: targetWindow?.getBounds() ?? null
    }
  })

  ipcMain.handle('window:set-always-on-top', (event, shouldStayOnTop) => {
    const targetWindow = getWindowFromEvent(event)

    if (!targetWindow) {
      return false
    }

    const isAlwaysOnTop = setAlwaysOnTopForPlatform(targetWindow, Boolean(shouldStayOnTop))

    scheduleWindowStateSave(targetWindow)

    return isAlwaysOnTop
  })

  ipcMain.on('window:start-resize', (event, edge) => {
    const targetWindow = getWindowFromEvent(event)

    if (!targetWindow) {
      return
    }

    startResizeLoop(targetWindow, edge)
  })

  ipcMain.on('window:stop-resize', () => {
    stopResizeLoop()
  })
}

/*
 * Cấp quyền microphone cho cửa sổ chính.
 */
function configureMediaPermissions() {
  session.defaultSession.setPermissionRequestHandler((webContents, permission, callback) => {
    const isAllowed = permission === 'media' && isMainWindowRenderer(webContents)

    callback(isAllowed)
  })

  session.defaultSession.setPermissionCheckHandler((webContents, permission) => {
    return permission === 'media' && isMainWindowRenderer(webContents)
  })
}

/*
 * Lấy danh sách màn hình hoặc cửa sổ
 * để renderer thu System Audio.
 */
function registerDesktopCaptureHandler() {
  ipcMain.removeHandler('get-sources')

  ipcMain.handle('get-sources', async (event, options = {}) => {
    if (!isMainWindowRenderer(event.sender)) {
      throw new Error('Nguồn yêu cầu không hợp lệ.')
    }

    const allowedTypes = ['screen', 'window']

    const requestedTypes = Array.isArray(options.types)
      ? options.types.filter((type) => allowedTypes.includes(type))
      : ['screen']

    const types = requestedTypes.length > 0 ? requestedTypes : ['screen']

    const sources = await desktopCapturer.getSources({
      types,
      thumbnailSize: {
        width: 0,
        height: 0
      },
      fetchWindowIcons: false
    })

    return sources.map((source) => ({
      id: source.id,
      name: source.name,
      displayId: source.display_id
    }))
  })
}

/*
 * Trên macOS, yêu cầu quyền microphone.
 * Quyền ghi màn hình cần được bật trong System Settings.
 */
async function requestMacPermissions() {
  if (!IS_MAC) {
    return
  }

  try {
    const microphoneStatus = systemPreferences.getMediaAccessStatus('microphone')

    if (microphoneStatus === 'not-determined') {
      const isGranted = await systemPreferences.askForMediaAccess('microphone')

      console.log(
        isGranted ? '✅ macOS đã cấp quyền microphone.' : '⚠️ macOS chưa cấp quyền microphone.'
      )
    } else {
      console.log(`🎤 Quyền microphone trên macOS: ${microphoneStatus}`)
    }

    const screenStatus = systemPreferences.getMediaAccessStatus('screen')

    console.log(`🖥 Quyền Screen Recording trên macOS: ${screenStatus}`)
  } catch (error) {
    console.error('❌ Không thể kiểm tra quyền macOS:', error)
  }
}

function createWindow() {
  const savedWindowState = readWindowState()

  const platformWindowOptions = IS_MAC
    ? {
        titleBarStyle: 'hiddenInset',
        trafficLightPosition: {
          x: 14,
          y: 16
        }
      }
    : {
        frame: false
      }

  mainWindow = new BrowserWindow({
    ...savedWindowState.bounds,

    minWidth: MIN_WIDTH,
    minHeight: MIN_HEIGHT,

    show: false,
    autoHideMenuBar: true,

    /*
     * Giữ cửa sổ trong suốt.
     * Việc resize được xử lý bằng resize handle riêng
     * thay vì dựa vào viền native.
     */
    transparent: true,
    backgroundColor: '#00000000',
    hasShadow: false,

    movable: true,
    resizable: false,

    minimizable: true,
    maximizable: true,
    closable: true,
    fullscreenable: false,

    alwaysOnTop: savedWindowState.alwaysOnTop,

    title: 'KaTOBA BridgeAI',

    ...platformWindowOptions,

    ...(IS_LINUX
      ? {
          icon
        }
      : {}),

    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),

      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,

      backgroundThrottling: false,
      navigateOnDragDrop: false
    }
  })

  setAlwaysOnTopForPlatform(mainWindow, savedWindowState.alwaysOnTop)

  mainWindow.on('ready-to-show', () => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.show()
    }
  })

  mainWindow.on('maximize', () => {
    stopResizeLoop()
    sendMaximizedState(mainWindow)
  })

  mainWindow.on('unmaximize', () => {
    sendMaximizedState(mainWindow)
  })

  mainWindow.on('restore', () => {
    sendMaximizedState(mainWindow)
  })

  mainWindow.on('move', () => {
    scheduleWindowStateSave(mainWindow)
  })

  mainWindow.on('resize', () => {
    scheduleWindowStateSave(mainWindow)
  })

  mainWindow.on('close', () => {
    stopResizeLoop()
    saveWindowState(mainWindow)
  })

  mainWindow.on('closed', () => {
    mainWindow = null
  })

  mainWindow.webContents.setWindowOpenHandler((details) => {
    shell.openExternal(details.url)

    return {
      action: 'deny'
    }
  })

  mainWindow.webContents.on('will-navigate', (event, url) => {
    const currentUrl = mainWindow?.webContents.getURL()

    if (currentUrl && url !== currentUrl) {
      event.preventDefault()
      shell.openExternal(url)
    }
  })

  if (is.dev && process.env['ELECTRON_RENDERER_URL']) {
    mainWindow.loadURL(process.env['ELECTRON_RENDERER_URL'])
  } else {
    mainWindow.loadFile(join(__dirname, '../renderer/index.html'))
  }
}

app.whenReady().then(async () => {
  electronApp.setAppUserModelId('com.kakusin.katoba-bridge-ai')

  app.on('browser-window-created', (_, window) => {
    optimizer.watchWindowShortcuts(window)
  })

  ipcMain.on('ping', () => {
    console.log('pong')
  })

  configureMediaPermissions()
  registerDesktopCaptureHandler()
  registerWindowControlHandlers()

  await requestMacPermissions()

  createWindow()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow()
    }
  })
})

app.on('window-all-closed', () => {
  if (!IS_MAC) {
    app.quit()
  }
})

app.on('before-quit', () => {
  stopResizeLoop()

  if (saveWindowStateTimer) {
    clearTimeout(saveWindowStateTimer)
    saveWindowStateTimer = null
  }

  ipcMain.removeHandler('get-sources')
  ipcMain.removeHandler('window:toggle-maximize')
  ipcMain.removeHandler('window:get-state')
  ipcMain.removeHandler('window:set-always-on-top')

  ipcMain.removeAllListeners('window:minimize')
  ipcMain.removeAllListeners('window:close')
  ipcMain.removeAllListeners('window:start-resize')
  ipcMain.removeAllListeners('window:stop-resize')
})
