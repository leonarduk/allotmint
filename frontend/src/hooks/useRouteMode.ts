import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useConfig } from '../ConfigContext'
import type { Mode } from '../modes'
import useFetch from './useFetch'
import { getGroups } from '../api'
import { normaliseGroupSlug } from '../utils/groups'
import { deriveModeFromPathname, pathForMode } from '../pageManifest'

interface RouteState {
  mode: Mode
  setMode: (mode: Mode) => void
  selectedOwner: string
  setSelectedOwner: (owner: string) => void
  selectedGroup: string
  setSelectedGroup: (group: string) => void
}

function deriveInitial() {
  const path = window.location.pathname.split('/').filter(Boolean)
  const params = new URLSearchParams(window.location.search)
  const mode = deriveModeFromPathname(window.location.pathname)
  const slug = path[1] ?? ''
  const owner = mode === 'owner' || mode === 'performance' ? slug : ''
  const group = mode === 'instrument' ? '' : normaliseGroupSlug(params.get('group'))

  return { mode, owner, group }
}

export function useRouteMode(): RouteState {
  const navigate = useNavigate()
  const location = useLocation()
  const { tabs, disabledTabs } = useConfig()
  const { data: groups } = useFetch(getGroups)

  const initial = deriveInitial()
  const [mode, setMode] = useState<Mode>(initial.mode)
  const [selectedOwner, setSelectedOwner] = useState(initial.owner)
  const [selectedGroup, setSelectedGroup] = useState(initial.group)

  useEffect(() => {
    const segs = location.pathname.split('/').filter(Boolean)
    const params = new URLSearchParams(location.search)
    const newMode = deriveModeFromPathname(location.pathname)
    const isDisabled = tabs[newMode] === false || disabledTabs?.includes(newMode)

    if (isDisabled) {
      const firstEnabled = Object.entries(tabs).find(
        ([candidateMode, enabled]) =>
          enabled !== false && !disabledTabs?.includes(candidateMode as Mode)
      )?.[0] as Mode | undefined

      if (firstEnabled) {
        setMode(firstEnabled)
        const targetPath = pathForMode(firstEnabled, {
          selectedOwner,
          selectedGroup,
        })
        if (location.pathname !== targetPath) {
          navigate(targetPath, { replace: true })
        }
      } else {
        console.warn('No enabled tabs available for navigation')
      }
      return
    }

    if (newMode === 'movers' && location.pathname !== '/movers') {
      setMode('movers')
      navigate('/movers', { replace: true })
      return
    }

    setMode(newMode)
    if (newMode === 'owner' || newMode === 'performance') {
      setSelectedOwner(segs[1] ?? '')
      return
    }

    if (newMode === 'instrument') {
      const slug = segs[1] ?? ''
      if (!slug) {
        setSelectedGroup('')
        return
      }
      if (groups) {
        const isValid = groups.some((group) => group.slug === slug)
        if (isValid) {
          setSelectedGroup(slug)
        } else {
          navigate(`/research/${slug}`, { replace: true })
        }
      }
      return
    }

    if (newMode === 'group') {
      setSelectedGroup(normaliseGroupSlug(params.get('group')))
    }
  }, [
    disabledTabs,
    groups,
    location.pathname,
    location.search,
    navigate,
    selectedGroup,
    selectedOwner,
    tabs,
  ])

  return {
    mode,
    setMode,
    selectedOwner,
    setSelectedOwner,
    selectedGroup,
    setSelectedGroup,
  }
}
