/**
 * afterPack — chạy sau khi electron-builder chép xong file vào bundle,
 * TRƯỚC bước ký. Đây là chỗ duy nhất sửa được quyền/thuộc tính của
 * extraResources mà không làm hỏng chữ ký sau đó.
 *
 * Hai việc phải làm trên macOS/Linux:
 *
 *  1. Trả lại bit thực thi cho backend PyInstaller.
 *     electron-builder giữ mode khi chép, nhưng nếu backend/dist/main từng
 *     đi qua zip, rsync sang máy khác, ổ exFAT/NTFS hay chia sẻ từ Windows
 *     thì bit +x biến mất -> spawn() ném EACCES và Electron chỉ log một dòng
 *     "Spawn backend thất bại" rồi im.
 *
 *  2. Gỡ com.apple.quarantine.
 *     File tải/giải nén từ máy khác mang cờ này. Gatekeeper chặn mọi
 *     executable lồng bên trong bundle bị quarantine -> backend bị giết
 *     ngay lúc exec, không có log.
 */
const { execFileSync } = require('node:child_process')
const { existsSync, chmodSync, readdirSync, statSync } = require('node:fs')
const { join } = require('node:path')

/** Đặt 0o755 cho file và mọi thứ bên trong nếu là thư mục. */
function makeExecutableTree(target) {
  const st = statSync(target)

  if (st.isDirectory()) {
    for (const entry of readdirSync(target)) {
      makeExecutableTree(join(target, entry))
    }
    chmodSync(target, 0o755)
    return
  }

  // Chỉ quan tâm file có khả năng bị exec/dlopen: binary chính và thư viện native.
  if (/\.(dylib|so)$/.test(target) || !/\.[a-z0-9]+$/i.test(target)) {
    chmodSync(target, 0o755)
  }
}

exports.default = async function afterPack(context) {
  const platform = context.electronPlatformName

  if (platform === 'win32') {
    return
  }

  const backendDir =
    platform === 'darwin'
      ? join(context.appOutDir, `${context.packager.appInfo.productFilename}.app`,
          'Contents', 'Resources', 'backend')
      : join(context.appOutDir, 'resources', 'backend')

  if (!existsSync(backendDir)) {
    console.warn(`[afterPack] Không thấy backend tại ${backendDir} — bỏ qua.`)
    return
  }

  makeExecutableTree(backendDir)
  console.log(`[afterPack] Đã đặt quyền thực thi cho ${backendDir}`)

  if (platform === 'darwin') {
    try {
      execFileSync('xattr', ['-cr', backendDir], { stdio: 'inherit' })
      console.log('[afterPack] Đã gỡ com.apple.quarantine khỏi backend')
    } catch (err) {
      console.warn(`[afterPack] xattr thất bại (bỏ qua): ${err.message}`)
    }
  }
}
