import { describe, it, expect } from 'vitest'
import {
  endsWithSep,
  isWindowsDriveRoot,
  isWindowsPath,
  lastSegment,
  pathSep,
  stripTrailingSep,
  withTrailingSep,
} from '../utils/fsPaths'

// The gateway may run on Windows or POSIX, so every decision is made from the
// SHAPE of the path — never from the browser's own platform.
describe('fsPaths', () => {
  describe('isWindowsPath', () => {
    it('recognises drive-letter and UNC paths', () => {
      expect(isWindowsPath('C:\\Users\\me')).toBe(true)
      expect(isWindowsPath('d:/projects')).toBe(true)
      expect(isWindowsPath('\\\\server\\share')).toBe(true)
    })

    it('does not claim a POSIX path containing a backslash', () => {
      // `\` is a legal filename character on POSIX.
      expect(isWindowsPath('/home/weird\\name')).toBe(false)
      expect(isWindowsPath('/home/me')).toBe(false)
    })
  })

  describe('pathSep', () => {
    it('is backslash for Windows-shaped paths and slash otherwise', () => {
      expect(pathSep('D:\\Kiro')).toBe('\\')
      expect(pathSep('\\\\srv\\share')).toBe('\\')
      expect(pathSep('/home/me')).toBe('/')
    })
  })

  describe('isWindowsDriveRoot', () => {
    it('matches only a bare drive root', () => {
      expect(isWindowsDriveRoot('C:\\')).toBe(true)
      expect(isWindowsDriveRoot('E:/')).toBe(true)
      expect(isWindowsDriveRoot('C:\\Users')).toBe(false)
      expect(isWindowsDriveRoot('/')).toBe(false)
    })
  })

  describe('stripTrailingSep', () => {
    it('keeps a Windows drive root intact', () => {
      // `C:` alone means the drive's CURRENT directory, not its root.
      expect(stripTrailingSep('C:\\')).toBe('C:\\')
      expect(stripTrailingSep('D:/')).toBe('D:/')
    })

    it('strips a trailing separator from a Windows path', () => {
      expect(stripTrailingSep('D:\\Kiro\\KiroCrew\\')).toBe('D:\\Kiro\\KiroCrew')
    })

    it('keeps the POSIX root and preserves a literal trailing backslash', () => {
      expect(stripTrailingSep('/')).toBe('/')
      expect(stripTrailingSep('/home/me/')).toBe('/home/me')
      expect(stripTrailingSep('/home/weird\\')).toBe('/home/weird\\')
    })
  })

  describe('withTrailingSep', () => {
    it('uses the native separator and never doubles it', () => {
      expect(withTrailingSep('D:\\Kiro')).toBe('D:\\Kiro\\')
      expect(withTrailingSep('D:\\')).toBe('D:\\')
      expect(withTrailingSep('/home/me')).toBe('/home/me/')
      expect(withTrailingSep('/')).toBe('/')
    })
  })

  describe('endsWithSep', () => {
    it('treats a trailing backslash as a separator only on a Windows path', () => {
      expect(endsWithSep('D:\\')).toBe(true)
      expect(endsWithSep('D:\\Kiro\\')).toBe(true)
      expect(endsWithSep('D:\\Kiro')).toBe(false)
      expect(endsWithSep('/home/weird\\')).toBe(false)
      expect(endsWithSep('/home/me/')).toBe(true)
    })
  })

  describe('lastSegment', () => {
    it('splits on the separators that apply to the path', () => {
      expect(lastSegment('D:\\Kiro\\KiroCrew')).toBe('KiroCrew')
      expect(lastSegment('C:/Users/me/proj')).toBe('proj')
      expect(lastSegment('/home/me/proj')).toBe('proj')
      expect(lastSegment('/home/weird\\name')).toBe('weird\\name')
    })
  })
})
