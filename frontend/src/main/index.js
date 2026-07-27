import {
  app,
  shell,
  BrowserWindow,
  ipcMain,
  desktopCapturer,
  session,
  systemPreferences
} from 'electron'

import { join } from 'path'
import { electronApp, optimizer, is } from '@electron-toolkit/utils'

import icon from '../../resources/icon.png?asset'

// Tắt tăng tốc phần cứng để hạn chế lỗi cửa sổ trong suốt trên Windows.
app.disableHardwareAcceleration()

let mainWindow = null

/**
 * Kiểm tra request quyền có đến từ cửa sổ chính của ứng dụng hay không.
 */
function isMainWindowRenderer(webContents) {
  return Boolean(
    mainWindow &&
    !mainWindow.isDestroyed() &&
    webContents &&
    webContents.id === mainWindow.webContents.id
  )
}

/**
 * Cấu hình quyền truy cập microphone cho renderer.
 *
 * Chỉ cửa sổ chính mới được cấp quyền media.
 * Các cửa sổ hoặc website bên ngoài sẽ bị từ chối.
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

/**
 * Đăng ký IPC lấy danh sách màn hình hoặc cửa sổ.
 *
 * Renderer chỉ cần source.id để capture System Audio,
 * nên không trả thumbnail để giảm dữ liệu truyền qua IPC.
 */
function registerDesktopCaptureHandler() {
  ipcMain.removeHandler('get-sources')

  ipcMain.handle('get-sources', async (_event, options = {}) => {
    const allowedTypes = ['screen', 'window']

    const requestedTypes = Array.isArray(options.types)
      ? options.types.filter((type) => allowedTypes.includes(type))
      : ['screen']

    const types = requestedTypes.length > 0 ? requestedTypes : ['screen']

    const sources = await desktopCapturer.getSources({
      types,

      /*
       * Renderer hiện chỉ dùng source.id.
       * Không tạo thumbnail để tiết kiệm bộ nhớ.
       */
      thumbnailSize: {
        width: 0,
        height: 0
      },

      fetchWindowIcons: false
    })

    return sources.map((source) => ({
      id: source.id,
      name: source.name
    }))
  })
}

/**
 * Yêu cầu quyền microphone trên macOS.
 *
 * Windows sẽ dùng quyền Microphone trong phần
 * Privacy & Security của hệ điều hành.
 */
async function requestMacMicrophonePermission() {
  if (process.platform !== 'darwin') {
    return
  }

  try {
    const isGranted = await systemPreferences.askForMediaAccess('microphone')

    if (isGranted) {
      console.log('✅ Đã được cấp quyền microphone trên macOS.')
    } else {
      console.warn('⚠️ Người dùng chưa cấp quyền microphone trên macOS.')
    }
  } catch (error) {
    console.error('❌ Không thể yêu cầu quyền microphone:', error)
  }
}

function createWindow() {
  mainWindow = new BrowserWindow({
    // Kích thước mặc định phù hợp với giao diện mới.
    width: 900,
    height: 340,

    // Không cho thu nhỏ cửa sổ quá mức.
    minWidth: 420,
    minHeight: 260,

    show: false,
    autoHideMenuBar: true,

    // Cửa sổ overlay trong suốt.
    transparent: true,
    backgroundColor: '#00000000',

    // Tắt thanh tiêu đề mặc định.
    frame: false,

    // Cho phép kéo và thay đổi kích thước.
    movable: true,
    resizable: true,

    // Cho phép thu nhỏ xuống taskbar.
    minimizable: true,

    // Không cho phóng toàn màn hình.
    maximizable: false,

    // Luôn nằm trên các ứng dụng khác.
    alwaysOnTop: true,

    /*
     * Không ẩn cửa sổ khi chuyển sang workspace khác.
     * Có ích với ứng dụng phụ đề overlay.
     */
    visibleOnAllWorkspaces: true,

    ...(process.platform === 'linux'
      ? {
          icon
        }
      : {}),

    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),

      /*
       * Giữ an toàn cho renderer:
       * không cho Vue truy cập trực tiếp Node.js.
       */
      contextIsolation: true,
      nodeIntegration: false,

      /*
       * Project hiện tại dùng preload của electron-toolkit,
       * nên chưa bật sandbox.
       */
      sandbox: false,

      /*
       * Audio phải tiếp tục chạy khi cửa sổ không được focus.
       */
      backgroundThrottling: false
    }
  })

  /*
   * Bảo đảm overlay luôn nằm trên cùng.
   */
  mainWindow.setAlwaysOnTop(true, 'screen-saver')

  mainWindow.on('ready-to-show', () => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.show()
    }
  })

  mainWindow.on('closed', () => {
    mainWindow = null
  })

  /*
   * Link bên ngoài sẽ mở bằng trình duyệt mặc định,
   * không mở bên trong Electron.
   */
  mainWindow.webContents.setWindowOpenHandler((details) => {
    shell.openExternal(details.url)

    return {
      action: 'deny'
    }
  })

  /*
   * Chặn việc Electron tự điều hướng sang website khác.
   */
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
  electronApp.setAppUserModelId('com.electron')

  app.on('browser-window-created', (_, window) => {
    optimizer.watchWindowShortcuts(window)
  })

  ipcMain.on('ping', () => {
    console.log('pong')
  })

  /*
   * Cấu hình quyền trước khi tạo cửa sổ.
   */
  configureMediaPermissions()

  /*
   * Đăng ký chức năng lấy nguồn System Audio.
   */
  registerDesktopCaptureHandler()

  /*
   * Trên macOS sẽ hiện yêu cầu quyền microphone.
   */
  await requestMacMicrophonePermission()

  createWindow()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow()
    }
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})

app.on('before-quit', () => {
  ipcMain.removeHandler('get-sources')
})
