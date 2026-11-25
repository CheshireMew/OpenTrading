import { ref } from 'vue'
import type { ResearchEventResponse } from './contracts'

export const alertNotices = ref<ResearchEventResponse[]>([])
export const alertDeliveryStatus = ref('')
let audio: AudioContext | undefined

export async function prepareAlertAudio() {
  try {
    audio ??= new AudioContext()
    if (audio.state === 'suspended') {
      // Autoplay blocking can leave resume() pending until a future gesture.
      // Do not hold notification delivery (or its cross-tab lock) indefinitely.
      await Promise.race([audio.resume(), new Promise(resolve => setTimeout(resolve, 200))])
    }
    return audio.state === 'running'
  } catch { return false }
}

export async function playAlertSound() {
  if (!await prepareAlertAudio() || !audio) return false
  const start = audio.currentTime
  for (const [offset, frequency] of [[0, 880], [0.22, 1174.66], [0.44, 880]]) {
    const oscillator = audio.createOscillator(), gain = audio.createGain()
    oscillator.type = 'sine'; oscillator.frequency.value = frequency!
    gain.gain.setValueAtTime(0, start + offset!)
    gain.gain.linearRampToValueAtTime(0.22, start + offset! + 0.02)
    gain.gain.exponentialRampToValueAtTime(0.001, start + offset! + 0.2)
    oscillator.connect(gain); gain.connect(audio.destination)
    oscillator.start(start + offset!); oscillator.stop(start + offset! + 0.21)
    oscillator.onended = () => { oscillator.disconnect(); gain.disconnect() }
  }
  return true
}

export async function enableAlertDelivery(sound: boolean, desktop: boolean) {
  // Start both directly in the click handler; permission/autoplay require a gesture.
  const audioReady = sound ? prepareAlertAudio() : Promise.resolve(true)
  const permission = desktop && 'Notification' in window && window.isSecureContext
    ? Notification.permission === 'default' ? Notification.requestPermission().catch(() => 'denied') : Promise.resolve(Notification.permission)
    : Promise.resolve(desktop ? 'unsupported' : 'off')
  const [ready, granted] = await Promise.all([audioReady, permission])
  alertDeliveryStatus.value = desktop && granted !== 'granted' ? granted === 'unsupported' ? 'alertNotificationsUnsupported' : 'alertNotificationsDenied'
    : !ready ? 'alertSoundBlocked' : ''
  window.dispatchEvent(new Event('opentrading:notification-permission'))
}

export function dismissAlertNotice(id: string) {
  alertNotices.value = alertNotices.value.filter(event => event.id !== id)
}

export async function deliverAlertEvent(event: ResearchEventResponse) {
  const channels: unknown = event.payload?.notificationChannels
  if (!Array.isArray(channels)) return
  if (channels.includes('in_app')) alertNotices.value = [...alertNotices.value.filter(item => item.id !== event.id), event].slice(-5)
  if (channels.includes('sound') && !await playAlertSound()) alertDeliveryStatus.value = 'alertSoundBlocked'
  if (channels.includes('windows') && 'Notification' in window && Notification.permission === 'granted') {
    try {
      const notification = new Notification(event.title, { body: event.body || event.symbol || '', tag: event.id, silent: channels.includes('sound') })
      notification.onclick = () => { window.focus(); window.dispatchEvent(new Event('opentrading:open-alerts')); notification.close() }
    } catch { alertDeliveryStatus.value = 'alertNotificationsUnsupported' }
  }
  window.dispatchEvent(new CustomEvent('opentrading:alert-triggered', { detail: event }))
}
