// Windows multi-drive browsing: a drive root has no parent, so walking up from
// C:\ can never reach D:\ or E:\. The picker gets a drives level ("This PC")
// from the roots the gateway reports, and typed navigation has to treat `\` as a
// separator on a Windows-shaped path.
//
// Nothing here assumes the test machine has a D: or E: — the drive list is what
// the mocked gateway says it is.
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import ProjectPicker from '../components/ProjectPicker'

const browseDirs = vi.fn()
const recentProjects = vi.fn()

vi.mock('../api/client', () => ({
  api: {
    browseDirs: (path?: string) => browseDirs(path),
    recentProjects: () => recentProjects(),
  },
}))

const anchorRect = {
  top: 100, bottom: 130, left: 100, right: 200, width: 100, height: 30, x: 100, y: 100,
  toJSON() {},
} as DOMRect

const WINDOWS_ROOTS = [
  { name: 'C:\\', path: 'C:\\' },
  { name: 'D:\\', path: 'D:\\' },
  { name: 'E:\\', path: 'E:\\' },
]

function open(onSelect: (p: string) => void = () => {}) {
  render(
    <ProjectPicker open onOpenChange={() => {}} anchorRect={anchorRect} onSelect={onSelect} />,
  )
}

describe('ProjectPicker Windows drives', () => {
  beforeEach(() => {
    browseDirs.mockReset()
    recentProjects.mockReset()
    // No recent projects -> the picker opens straight on the Browse tab.
    recentProjects.mockResolvedValue({ dirs: [] })
  })

  it('offers the drives level at a Windows drive root', async () => {
    browseDirs.mockResolvedValue({
      path: 'C:\\', parent: 'C:\\', dirs: [{ name: 'Users', path: 'C:\\Users' }],
      isRoot: true, roots: WINDOWS_ROOTS,
    })
    open()
    const drives = await screen.findByLabelText('This PC')
    fireEvent.click(drives)
    // Every accessible drive is a top-level row.
    await waitFor(() => expect(screen.getByText('D:\\')).toBeInTheDocument())
    expect(screen.getByText('C:\\')).toBeInTheDocument()
    expect(screen.getByText('E:\\')).toBeInTheDocument()
  })

  it('browses into a drive picked from the drives level', async () => {
    browseDirs.mockResolvedValueOnce({
      path: 'C:\\', parent: 'C:\\', dirs: [], isRoot: true, roots: WINDOWS_ROOTS,
    })
    open()
    fireEvent.click(await screen.findByLabelText('This PC'))
    browseDirs.mockResolvedValueOnce({
      path: 'D:\\', parent: 'D:\\', dirs: [{ name: 'Kiro', path: 'D:\\Kiro' }],
      isRoot: true, roots: WINDOWS_ROOTS,
    })
    fireEvent.click(await screen.findByText('D:\\'))
    await waitFor(() => expect(browseDirs).toHaveBeenCalledWith('D:\\'))
    // And the drive's own directories are now listed.
    await waitFor(() => expect(screen.getByText('Kiro')).toBeInTheDocument())
  })

  it('drills into a typed drive root (trailing backslash is a separator)', async () => {
    browseDirs.mockResolvedValue({
      path: 'C:\\Users\\me', parent: 'C:\\Users', dirs: [], isRoot: false, roots: WINDOWS_ROOTS,
    })
    open()
    const input = await screen.findByRole('combobox')
    await waitFor(() => expect((input as HTMLInputElement).value).toBe('C:\\Users\\me\\'))
    fireEvent.change(input, { target: { value: 'D:\\' } })
    // Debounced, so allow the timer to fire.
    await waitFor(() => expect(browseDirs).toHaveBeenCalledWith('D:\\'), { timeout: 2000 })
  })

  it('drills into a typed nested Windows path', async () => {
    browseDirs.mockResolvedValue({
      path: 'C:\\Users\\me', parent: 'C:\\Users', dirs: [], isRoot: false, roots: WINDOWS_ROOTS,
    })
    open()
    const input = await screen.findByRole('combobox')
    fireEvent.change(input, { target: { value: 'D:\\Kiro\\' } })
    await waitFor(() => expect(browseDirs).toHaveBeenCalledWith('D:\\Kiro'), { timeout: 2000 })
  })

  it('commits the selected project path with no trailing separator', async () => {
    const onSelect = vi.fn()
    browseDirs.mockResolvedValue({
      path: 'D:\\Kiro\\KiroCrew', parent: 'D:\\Kiro', dirs: [], isRoot: false, roots: WINDOWS_ROOTS,
    })
    open(onSelect)
    const input = await screen.findByRole('combobox')
    await waitFor(() => expect((input as HTMLInputElement).value).toBe('D:\\Kiro\\KiroCrew\\'))
    fireEvent.keyDown(input, { key: 'Enter', metaKey: true })
    expect(onSelect).toHaveBeenCalledWith('D:\\Kiro\\KiroCrew')
  })

  it('filters the listing by the typed Windows segment', async () => {
    browseDirs.mockResolvedValue({
      path: 'D:\\Kiro',
      parent: 'D:\\',
      dirs: [
        { name: 'KiroCrew', path: 'D:\\Kiro\\KiroCrew' },
        { name: 'other', path: 'D:\\Kiro\\other' },
      ],
      isRoot: false,
      roots: WINDOWS_ROOTS,
    })
    open()
    const input = await screen.findByRole('combobox')
    fireEvent.change(input, { target: { value: 'D:\\Kiro\\Kiro' } })
    await waitFor(() => expect(screen.queryByText('other')).not.toBeInTheDocument())
    expect(screen.getByText('KiroCrew')).toBeInTheDocument()
  })

  it('keeps POSIX behavior unchanged: no drives level at /', async () => {
    browseDirs.mockResolvedValue({
      path: '/', parent: '/', dirs: [{ name: 'home', path: '/home' }],
      isRoot: true, roots: [{ name: '/', path: '/' }],
    })
    open()
    await screen.findByText('home')
    // One root means there is nothing above `/` to show.
    expect(screen.queryByLabelText('This PC')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Back')).not.toBeInTheDocument()
  })

  it('tolerates a gateway response with no roots field', async () => {
    // Backward compatibility: an older gateway omits isRoot/roots entirely.
    browseDirs.mockResolvedValue({
      path: '/home/u', parent: '/home', dirs: [{ name: 'proj', path: '/home/u/proj' }],
    })
    open()
    expect(await screen.findByText('proj')).toBeInTheDocument()
    expect(screen.queryByLabelText('This PC')).not.toBeInTheDocument()
  })
})
