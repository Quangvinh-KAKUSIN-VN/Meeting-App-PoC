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
import { spawn, spawnSync } from 'node:child_process'
import net from 'node:net'
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

// ============================================================
// SINGLE INSTANCE LOCK — chặn mở nhiều app cùng lúc
// (tránh spawn nhiều backend -> tốn gấp đôi RAM,
// và tránh lệch ipcMain giữa các tiến trình gây "No handler registered")
// ============================================================
const gotSingleInstanceLock = app.requestSingleInstanceLock()

if (!gotSingleInstanceLock) {
  app.quit()
} else {
  app.on('second-instance', () => {
    // Người dùng mở app lần 2 -> đưa cửa sổ hiện có lên trước, không mở thêm
    if (mainWindow) {
      if (mainWindow.isMinimized()) {
        mainWindow.restore()
      }
      mainWindow.focus()
    }
  })
}

let resizeState = null
let resizeTimer = null
let saveWindowStateTimer = null

// Phân biệt "backend chết vì mình đang tắt app" với "backend crash".
// Thiếu cờ này thì lúc thoát app sẽ bắn nhầm sự kiện backend:down cho renderer.
let isQuitting = false

// ============================================================
// KHỞI ĐỘNG / TẮT BACKEND
// ============================================================

let backendProcess = null

/*
 * Đặt true để test spawn backend ngay khi chạy dev (npm run dev).
 * Khi test: ĐỪNG chạy python main.py song song (trùng cổng 8765).
 * Bản production (đã đóng gói) LUÔN tự spawn, không phụ thuộc cờ này.
 */
const SPAWN_BACKEND_IN_DEV = false

/*
 * NGUỒN SỰ THẬT DUY NHẤT cho cổng backend.
 *
 * Giá trị này được truyền xuống tiến trình Python qua biến môi trường
 * KATOBA_PORT, nên chỉ cần sửa ở đây là cả hai phía cùng đổi.
 *
 * Renderer lấy cổng qua IPC 'backend:get-endpoint' — đừng viết cứng
 * ws://127.0.0.1:8765 trong renderer nữa.
 */
const BACKEND_PORT = 8765
const BACKEND_HOST = '127.0.0.1'

// Nạp 3 model ONNX/CTranslate2 trên CPU. Máy cấu hình thấp (i5-8250U, 8GB,
// không GPU) có thể mất hơn 30 giây -> để 90s cho chắc.
const BACKEND_READY_TIMEOUT_MS = 90000

// PyInstaller sinh main.exe trên Windows, main (không đuôi) trên macOS/Linux.
const BACKEND_EXE = IS_WINDOWS ? 'main.exe' : 'main'

function getBackendDir() {
  if (app.isPackaged) {
    // production: electron-builder chép backend vào resources/backend (extraResources)
    return join(process.resourcesPath, 'backend')
  }
  // dev: dùng bản build ở backend/dist/main (chạy npm run dev từ thư mục frontend/)
  return join(process.cwd(), '..', 'backend', 'dist', 'main')
}

function shouldSpawnBackend() {
  return app.isPackaged || SPAWN_BACKEND_IN_DEV
}

/**
 * Trả true nếu đã spawn được, false nếu không tìm thấy file.
 * Nhờ giá trị trả về mà bên gọi không phải chờ vô ích 90 giây.
 */
function startBackend() {
  const dir = getBackendDir()
  const exePath = join(dir, BACKEND_EXE)

  if (!existsSync(exePath)) {
    console.error(`❌ Không tìm thấy backend tại: ${exePath}`)
    return false
  }

  console.log(`🚀 Khởi động backend: ${exePath}`)
  console.log(`📁 cwd: ${dir}`)
  console.log(`🔌 Cổng: ${BACKEND_HOST}:${BACKEND_PORT}`)

  backendProcess = spawn(exePath, [], {
    cwd: dir,
    windowsHide: true,
    stdio: ['ignore', 'pipe', 'pipe'],
    env: {
      ...process.env,
      PYTHONUTF8: '1',
      PYTHONIOENCODING: 'utf-8',

      // main.py đọc hai biến này -> khỏi phải sửa cổng ở hai nơi
      KATOBA_HOST: BACKEND_HOST,
      KATOBA_PORT: String(BACKEND_PORT),

      /*
       * Ghi transcript ra đĩa mặc định TẮT.
       *
       * Nội dung họp doanh nghiệp không nên nằm dưới dạng văn bản thuần
       * trong thư mục cài đặt. Chỉ bật khi cần thu thập dữ liệu để bổ sung
       * glossary, và nhớ tắt lại.
       */
      KATOBA_TRANSCRIPT_LOG: '0',
      KATOBA_VERBOSE: is.dev ? '1' : '0'
    }
  })

  backendProcess.stdout?.on('data', (d) => console.log(`[backend] ${d.toString().trim()}`))
  backendProcess.stderr?.on('data', (d) => console.error(`[backend-err] ${d.toString().trim()}`))

  backendProcess.on('error', (err) => {
    console.error(`❌ Spawn backend thất bại: ${err.message}`)
    backendProcess = null
  })

  backendProcess.on('exit', (code, signal) => {
    console.log(`[backend] đã thoát (code=${code}, signal=${signal})`)
    backendProcess = null

    /*
     * Báo cho renderer biết backend đã chết.
     *
     * Không có tín hiệu này, renderer cứ thử reconnect mù rồi bỏ cuộc
     * mà không hiểu vì sao — chính là triệu chứng của BUG-026.
     */
    if (!isQuitting && mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('backend:down', { code, signal })
    }
  })

  return true
}

function stopBackend() {
  if (!backendProcess || backendProcess.killed) {
    return
  }

  const pid = backendProcess.pid
  backendProcess = null // chặn will-quit gọi lại lần nữa

  console.log('🛑 Tắt backend...')

  if (IS_WINDOWS) {
    /*
     * taskkill /T giết cả CÂY tiến trình, /F là cưỡng bức.
     *
     * Build onedir hiện tại thì kill() thường cũng đủ, vì main.exe chính là
     * tiến trình thật. Nhưng nếu sau này đổi sang PyInstaller onefile,
     * bootloader sẽ giải nén ra %TEMP%\_MEIxxxxx rồi spawn một tiến trình
     * con — giết cha thì con vẫn sống và thư mục temp không được dọn.
     * Dùng /T ngay từ bây giờ để khỏi phải nhớ lúc đổi cấu hình build.
     *
     * spawnSync chặn đồng bộ nên khi before-quit trả về là cây tiến trình
     * đã chết hẳn, không cần event.preventDefault().
     */
    try {
      spawnSync('taskkill', ['/pid', String(pid), '/T', '/F'], { windowsHide: true })
    } catch (err) {
      console.warn(`taskkill thất bại (${err.message}), thử process.kill()`)
      try {
        process.kill(pid)
      } catch {
        /* tiến trình đã chết */
      }
    }
  } else {
    try {
      process.kill(pid, 'SIGTERM')
    } catch {
      /* tiến trình đã chết */
    }
  }
}

/**
 * Chờ backend mở cổng. Thoát sớm nếu tiến trình đã chết.
 */
function waitForPort(port, host, timeoutMs) {
  return new Promise((resolve) => {
    const start = Date.now()

    const attempt = () => {
      // Backend crash lúc khởi động -> đừng chờ hết 90 giây vô ích
      if (shouldSpawnBackend() && !backendProcess) {
        resolve(false)
        return
      }

      const socket = net.connect(port, host)

      /*
       * Bắt buộc phải có.
       *
       * Nếu firewall chặn kiểu DROP (không trả RST), 'error' sẽ không bao
       * giờ bắn và vòng lặp retry đứng im vĩnh viễn.
       */
      socket.setTimeout(2000)

      const retry = () => {
        socket.destroy()

        if (Date.now() - start > timeoutMs) {
          resolve(false)
        } else {
          setTimeout(attempt, 500)
        }
      }

      socket.once('connect', () => {
        socket.destroy()
        resolve(true)
      })

      socket.once('timeout', retry)
      socket.once('error', retry)
    }

    attempt()
  })
}

// ============================================================
// TRẠNG THÁI CỬA SỔ
// ============================================================

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
 * Renderer hỏi cổng backend qua đây thay vì viết cứng URL.
 * Đổi BACKEND_PORT ở trên là cả ba tầng cùng đổi theo.
 */
function registerBackendHandlers() {
  ipcMain.removeHandler('backend:get-endpoint')
  ipcMain.removeHandler('backend:is-running')

  ipcMain.handle('backend:get-endpoint', (event) => {
    if (!isMainWindowRenderer(event.sender)) {
      throw new Error('Nguồn yêu cầu không hợp lệ.')
    }

    return {
      host: BACKEND_HOST,
      port: BACKEND_PORT,
      wsJa: `ws://${BACKEND_HOST}:${BACKEND_PORT}/ws/audio/ja`,
      wsVi: `ws://${BACKEND_HOST}:${BACKEND_PORT}/ws/audio/vi`,
      httpBase: `http://${BACKEND_HOST}:${BACKEND_PORT}`
    }
  })

  ipcMain.handle('backend:is-running', () => Boolean(backendProcess))
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
  /*
   * Instance thứ hai: app.quit() ở đầu file KHÔNG dừng module,
   * nên nếu không chặn ở đây thì nó vẫn chạy tiếp và spawn thêm
   * một backend nữa trước khi thoát — đúng thứ single instance lock
   * sinh ra để tránh.
   */
  if (!gotSingleInstanceLock) {
    return
  }

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
  registerBackendHandlers()

  await requestMacPermissions()

  if (shouldSpawnBackend()) {
    if (startBackend()) {
      const ready = await waitForPort(BACKEND_PORT, BACKEND_HOST, BACKEND_READY_TIMEOUT_MS)

      if (ready) {
        console.log(`✅ Backend sẵn sàng ở cổng ${BACKEND_PORT}.`)
      } else {
        console.error(
          `❌ Backend không mở cổng ${BACKEND_PORT} sau ${BACKEND_READY_TIMEOUT_MS / 1000}s.`
        )
      }
    }
  }

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
  isQuitting = true

  stopResizeLoop()

  if (saveWindowStateTimer) {
    clearTimeout(saveWindowStateTimer)
    saveWindowStateTimer = null
  }

  ipcMain.removeHandler('get-sources')
  ipcMain.removeHandler('window:toggle-maximize')
  ipcMain.removeHandler('window:get-state')
  ipcMain.removeHandler('window:set-always-on-top')
  ipcMain.removeHandler('backend:get-endpoint')
  ipcMain.removeHandler('backend:is-running')

  ipcMain.removeAllListeners('window:minimize')
  ipcMain.removeAllListeners('window:close')
  ipcMain.removeAllListeners('window:start-resize')
  ipcMain.removeAllListeners('window:stop-resize')

  stopBackend()
})

// Lưới an toàn: đảm bảo backend bị tắt kể cả khi app thoát bất thường.
app.on('will-quit', () => {
  isQuitting = true
  stopBackend()
})
