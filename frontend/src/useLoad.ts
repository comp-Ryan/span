import { useEffect, useState } from 'react'

/** Fetch on mount and when `key` changes; `reload()` refetches (used by Retry buttons). */
export function useLoad<T>(load: () => Promise<T>, key: string) {
  const [state, setState] = useState<{ data: T | null; error: string | null; loading: boolean }>({ data: null, error: null, loading: true })
  const [tick, setTick] = useState(0)
  useEffect(() => {
    let stale = false
    setState(s => ({ data: s.data, error: null, loading: true }))
    load().then(data => { if (!stale) setState({ data, error: null, loading: false }) })
      .catch(e => { if (!stale) setState(s => ({ data: s.data, error: e instanceof Error ? e.message : String(e), loading: false })) })
    return () => { stale = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, tick])
  return { ...state, reload: () => setTick(t => t + 1) }
}
