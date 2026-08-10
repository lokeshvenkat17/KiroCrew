// Path helpers shared by the directory-browsing pickers (ProjectPicker,
// WorkspacePicker). The gateway may run on Windows OR POSIX and the dashboard
// is served to a browser that knows neither, so every decision here is made
// from the SHAPE of the path the backend returned — never from the client's
// own platform, which is irrelevant to where the files live.

/** True for a Windows-shaped absolute path: a drive letter (`C:…`) or a UNC share (`\\srv\share`). */
export function isWindowsPath(path: string): boolean {
  return /^[A-Za-z]:/.test(path) || path.startsWith('\\\\')
}

/**
 * The path separator to use for *path*.
 *
 * `\` is a separator ONLY on a Windows-shaped path. On POSIX it is a legal
 * filename character, so a trailing `\` there belongs to the directory name and
 * must never be treated as a delimiter.
 */
export function pathSep(path: string): '\\' | '/' {
  return isWindowsPath(path) ? '\\' : '/'
}

/** True for a bare Windows drive root — `C:\` or `C:/`. */
export function isWindowsDriveRoot(path: string): boolean {
  return /^[A-Za-z]:[\\/]$/.test(path)
}

/**
 * Strip the trailing separator a browse step appends for typing continuation.
 *
 * Roots survive intact: POSIX `/` stays `/`, and a Windows drive root stays
 * `C:\` because trimming it to `C:` would silently mean the drive's *current
 * directory* rather than its root.
 */
export function stripTrailingSep(path: string): string {
  if (isWindowsPath(path)) {
    return isWindowsDriveRoot(path) ? path : path.replace(/[\\/]+$/, '')
  }
  return path.replace(/\/+$/, '') || '/'
}

/** Append the native separator unless *path* already ends in one. */
export function withTrailingSep(path: string): string {
  const sep = pathSep(path)
  return path.endsWith(sep) ? path : path + sep
}

/**
 * True when *path* looks like a directory the user has finished typing — i.e.
 * it ends in that path flavour's separator, so the browser should descend into
 * it instead of filtering the current listing by the last segment.
 */
export function endsWithSep(path: string): boolean {
  return path.endsWith(pathSep(path))
}

/** The last path segment of *path*, split on whichever separators apply. */
export function lastSegment(path: string): string {
  const parts = isWindowsPath(path) ? path.split(/[\\/]/) : path.split('/')
  return parts.pop() || ''
}
