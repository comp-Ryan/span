export type VoiceStatus = 'idle' | 'listening' | 'error'

type RecognitionResult = { transcript: string }
type RecognitionEvent = { results: ArrayLike<ArrayLike<RecognitionResult>> }
type RecognitionErrorEvent = { error: string }

export interface SpeechRecognitionLike {
  continuous: boolean
  interimResults: boolean
  lang: string
  onresult: ((event: RecognitionEvent) => void) | null
  onerror: ((event: RecognitionErrorEvent) => void) | null
  onend: (() => void) | null
  start(): void
  stop(): void
  abort(): void
}

type RecognitionConstructor = new () => SpeechRecognitionLike

export function recognitionUnavailableMessage(secureContext = true) {
  if (!secureContext) return 'Browser voice needs localhost or HTTPS. You can still type your question.'
  return 'Speech recognition is not available in this browser. Try a supported browser or type your question.'
}

export function recognitionErrorMessage(error: string) {
  if (error === 'not-allowed' || error === 'service-not-allowed') {
    return 'Microphone access was denied. Allow microphone access, then try again, or type your question.'
  }
  if (error === 'no-speech') return 'No speech was detected. Try the microphone again or type your question.'
  if (error === 'audio-capture') return 'No microphone was found. Connect a microphone or type your question.'
  return 'Speech recognition stopped unexpectedly. Try again or type your question.'
}

export function speechRecognitionConstructor(): RecognitionConstructor | null {
  if (typeof window === 'undefined') return null
  const speechWindow = window as Window & {
    SpeechRecognition?: RecognitionConstructor
    webkitSpeechRecognition?: RecognitionConstructor
  }
  return speechWindow.SpeechRecognition || speechWindow.webkitSpeechRecognition || null
}

/** Starts one explicit, single-utterance recognition session. */
export function listenOnce(
  onText: (text: string) => void,
  onStatus: (status: VoiceStatus, message?: string) => void,
): () => void {
  const Constructor = speechRecognitionConstructor()
  if (!Constructor) {
    onStatus('error', recognitionUnavailableMessage(
      typeof window === 'undefined' || window.isSecureContext || location.hostname === 'localhost' || location.hostname === '127.0.0.1',
    ))
    return () => {}
  }
  let recognition: SpeechRecognitionLike
  let failed = false
  try {
    recognition = new Constructor()
    recognition.continuous = false
    recognition.interimResults = false
    recognition.lang = 'en-US'
    recognition.onresult = event => {
      const text = event.results[0]?.[0]?.transcript.trim()
      if (text) onText(text)
    }
    recognition.onerror = event => { failed = true; onStatus('error', recognitionErrorMessage(event.error)) }
    recognition.onend = () => { if (!failed) onStatus('idle') }
    onStatus('listening')
    recognition.start()
  } catch {
    onStatus('error', 'Could not start speech recognition. Check microphone access or type your question.')
    return () => {}
  }
  return () => {
    recognition.onresult = null
    recognition.onerror = null
    recognition.onend = null
    try { recognition.abort() } catch { /* browser may already have ended it */ }
  }
}

/** Stable persisted event IDs prevent replayed speech from being spoken again this tab session. */
export function claimSpeechEvent(eventId: string | undefined, storage: Pick<Storage, 'getItem' | 'setItem'>): boolean {
  if (!eventId) return false
  const key = `span.browserVoice.spoken.${eventId}`
  if (storage.getItem(key)) return false
  storage.setItem(key, '1')
  return true
}

export function assistantSpeechText(event: { event: string; data?: { text?: unknown; kind?: string; speaker?: string } }) {
  const data = event.data
  if (event.event !== 'speech' || data?.kind === 'caller' || data?.speaker === 'caller') return ''
  return typeof data?.text === 'string' ? data.text.trim() : ''
}

export function approvalChoice(
  text: string,
  options: Array<{ id: string; label: string }>,
): string | undefined {
  const normalize = (value: string) => value.toLowerCase()
    .replace(/[’]/g, "'")
    .replace(/[.!?,;:]+/g, '')
    .replace(/\s+/g, ' ')
    .trim()
  const spoken = normalize(text)
  if (!spoken) return undefined

  // Exact option wording is explicit; otherwise accept only short, direct approval or decline phrases.
  const exact = options.filter(option => normalize(option.label) === spoken)
  if (exact.length === 1) return exact[0].id
  if (exact.length > 1) return undefined

  const affirmative = new Set(['yes', 'yes please', 'approve', 'approved', 'i approve', 'go ahead', 'do it'])
  const negative = new Set(['no', 'no thanks', 'decline', 'i decline', 'reject', 'not now', 'cancel'])
  const category = affirmative.has(spoken) ? 'yes' : negative.has(spoken) ? 'no' : spokenCategory(spoken)
  if (!category) return undefined

  const matches = options.filter(option => {
    const id = normalize(option.id)
    const label = normalize(option.label)
    return category === 'yes'
      ? id === 'yes' || /\b(yes|approve|approved|accept|confirm)\b/.test(label)
      : id === 'no' || /\b(no|decline|reject|not now|cancel)\b/.test(label)
  })
  return matches.length === 1 ? matches[0].id : undefined
}

/** The owner's own words: "Yeah please send them out" is a yes, "no don't text anyone" is a no. A hedge ("but", "if",
 *  "only") or a question after the yes/no keeps it a question: Span never acts on an uncertain approval. */
function spokenCategory(spoken: string): 'yes' | 'no' | undefined {
  const hedge = /\b(but|if|unless|only|maybe|except|however|although|what about|as long as)\b/
  const question = /^(what|why|how|when|where|which|who|is|are|can|could|should|would|will|does|did|am|do (you|we|they|i))\b/  // "do it" is an instruction, "do you think" a question
  const yes = spoken.match(/^(yes|yeah|yep|yup|ok|okay|sure thing)\b\s*(.*)$/)
  if (yes) return yes[2] && (hedge.test(yes[2]) || question.test(yes[2])) ? undefined : (yes[2] || /^(ok|okay)$/.test(yes[1]) === false ? 'yes' : undefined)
  const no = spoken.match(/^(no|nope|nah|not now|not yet|hold off|don't|do not|cancel|skip)\b\s*(.*)$/)
  if (no) return no[2] && (hedge.test(no[2]) || question.test(no[2])) ? undefined : 'no'
  if (/^(please\s+)?(go ahead|do it|send (them|it|the reminders|the texts)( out)?|text them( all)?|yes do that)\b/.test(spoken) && !hedge.test(spoken)) return 'yes'
  return undefined
}
