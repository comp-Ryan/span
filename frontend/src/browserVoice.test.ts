import { describe, expect, it } from 'vitest'
import { approvalChoice, assistantSpeechText, claimSpeechEvent, recognitionErrorMessage, recognitionUnavailableMessage } from './browserVoice'

describe('browser voice helpers', () => {
  it('explains unsupported or insecure speech recognition and recoverable errors', () => {
    expect(recognitionUnavailableMessage()).toMatch(/not available/)
    expect(recognitionUnavailableMessage(false)).toMatch(/localhost or HTTPS/)
    expect(recognitionErrorMessage('not-allowed')).toMatch(/denied/)
    expect(recognitionErrorMessage('no-speech')).toMatch(/No speech/)
  })

  it('claims persisted speech event IDs only once per session', () => {
    const entries = new Map<string, string>()
    const storage = {
      getItem: (key: string) => entries.get(key) ?? null,
      setItem: (key: string, value: string) => { entries.set(key, value) },
    }
    expect(claimSpeechEvent(undefined, storage)).toBe(false)
    expect(claimSpeechEvent('event-1', storage)).toBe(true)
    expect(claimSpeechEvent('event-1', storage)).toBe(false)
    expect(claimSpeechEvent('event-2', storage)).toBe(true)
  })

  it('only returns assistant speech and never caller speech', () => {
    expect(assistantSpeechText({ event: 'speech', data: { text: '  You are covered. ' } })).toBe('You are covered.')
    expect(assistantSpeechText({ event: 'speech', data: { text: 'What do you mean?', kind: 'caller' } })).toBe('')
    expect(assistantSpeechText({ event: 'speech', data: { text: 'What do you mean?', speaker: 'caller' } })).toBe('')
    expect(assistantSpeechText({ event: 'node.update', data: { text: 'Not speech' } })).toBe('')
  })

  it('parses only unambiguous explicit approval and decline choices', () => {
    const options = [
      { id: 'yes', label: 'Yes, text them' },
      { id: 'chase_only', label: "Text, don't touch bills" },
      { id: 'no', label: 'Not now' },
    ]
    expect(approvalChoice('Yes, please.', options)).toBe('yes')
    expect(approvalChoice('not now', options)).toBe('no')
    expect(approvalChoice("text, don't touch bills", options)).toBe('chase_only')
    expect(approvalChoice('Maybe yes, but only if they agree', options)).toBeUndefined()
    expect(approvalChoice('sure', options)).toBeUndefined()
    expect(approvalChoice('yes', [{ id: 'a', label: 'Approve' }, { id: 'b', label: 'Yes please' }])).toBeUndefined()
  })
})

describe('spoken approvals in the owner\'s own words', () => {
  const options = [{ id: 'yes', label: 'Yes, text them' }, { id: 'chase_only', label: "Text, don't touch bills" }, { id: 'no', label: 'Not now' }]
  it('a leading yes followed by an instruction is an approval', () => {
    expect(approvalChoice('Yes you can you draft up some reminders', options)).toBe('yes')
    expect(approvalChoice('Yeah please send them out', options)).toBe('yes')
    expect(approvalChoice('Yep, go for it.', options)).toBe('yes')
    expect(approvalChoice('okay do it', options)).toBe('yes')
  })
  it('a plain instruction to send or text them is an approval', () => {
    expect(approvalChoice('go ahead and text them', options)).toBe('yes')
    expect(approvalChoice('send them out', options)).toBe('yes')
    expect(approvalChoice('please send the reminders', options)).toBe('yes')
  })
  it('a leading no, or hold off, is a decline', () => {
    expect(approvalChoice("no don't text anyone", options)).toBe('no')
    expect(approvalChoice('hold off for now', options)).toBe('no')
    expect(approvalChoice('Nope, not yet', options)).toBe('no')
  })
  it('hedges and questions after a yes are still questions, never approvals', () => {
    expect(approvalChoice('yes but only if they agree', options)).toBeUndefined()
    expect(approvalChoice('Yes, is Hearth reliable?', options)).toBeUndefined()
    expect(approvalChoice("why don't we do that why don't we look at overdue invoices first", options)).toBeUndefined()
    expect(approvalChoice('yes if the forecast holds', options)).toBeUndefined()
    expect(approvalChoice('no what about Evergreen', options)).toBeUndefined()
  })
})
