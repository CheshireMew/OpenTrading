<template>
  <div class="app-page referral-page">
    <div class="app-page-inner referral-inner">
      <header class="app-page-header">
        <h1 class="app-title">{{ t('referrals.title') }}</h1>
        <p class="app-subtitle referral-intro">{{ t('referrals.intro') }}</p>
      </header>

      <section v-for="section in sections" :key="section.id" :aria-labelledby="'referral-' + section.id">
        <div class="referral-section-heading">
          <h2 :id="'referral-' + section.id" class="app-section-title">{{ t('referrals.' + section.id) }}</h2>
          <span v-if="section.id === 'exchanges'" class="referral-benefit">{{ t('referrals.exchangeBenefit') }}</span>
        </div>
        <div class="referral-grid">
          <article v-for="provider in section.providers" :key="provider.url" class="app-panel referral-card">
            <header class="referral-provider">
              <div class="referral-provider-name">
                <span class="referral-icon"><component :is="section.icon" aria-hidden="true" /></span>
                <h3>{{ t('referrals.' + provider.name) }}</h3>
              </div>
              <a :href="provider.url" target="_blank" rel="noopener noreferrer" :class="section.id === 'exchanges' ? 'app-button-primary' : 'app-button-secondary'">
                {{ t('referrals.' + section.action) }}<ArrowUpRightIcon aria-hidden="true" />
              </a>
            </header>
            <dl class="referral-codes">
              <div v-for="code in provider.codes" :key="code.value">
                <dt>{{ t('referrals.' + code.label) }}</dt>
                <dd>
                  <button type="button" class="referral-copy" :aria-label="t(copied === code.value ? 'referrals.copied' : 'referrals.copyCode', { code: code.value })" @click="copyCode(code.value)">
                    <code>{{ code.value }}</code>
                    <CheckIcon v-if="copied === code.value" aria-hidden="true" /><ClipboardDocumentIcon v-else aria-hidden="true" />
                  </button>
                </dd>
              </div>
            </dl>
          </article>
        </div>
      </section>

      <section aria-labelledby="referral-resources">
        <div class="referral-section-heading"><h2 id="referral-resources" class="app-section-title">{{ t('referrals.communityAndLearning') }}</h2></div>
        <div class="referral-grid">
          <a v-for="resource in resources" :key="resource.url" :href="resource.url" target="_blank" rel="noopener noreferrer" class="app-panel referral-resource">
            <span class="referral-icon"><component :is="resource.icon" aria-hidden="true" /></span>
            <div><h3>{{ t('referrals.' + resource.name) }}</h3><p>{{ resource.address }}</p></div>
            <ArrowUpRightIcon class="referral-resource-arrow" aria-hidden="true" />
          </a>
        </div>
      </section>
      <p v-if="copyError" class="referral-copy-error" role="alert">{{ t('referrals.copyFailed') }}</p>
      <span class="sr-only" role="status">{{ copied ? t('referrals.copied', { code: copied }) : '' }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ArrowUpRightIcon, BookOpenIcon, BuildingLibraryIcon, ChatBubbleLeftRightIcon, CheckIcon, ClipboardDocumentIcon, WalletIcon } from '@heroicons/vue/24/outline'

defineOptions({ name: 'ReferralLinks' })
const { t } = useI18n()
const sections = [
  { id: 'exchanges', icon: BuildingLibraryIcon, action: 'register', providers: [
    { name: 'binance', url: 'https://binance.com/join?ref=SRXT5KUM', codes: [{ label: 'inviteCode', value: 'SRXT5KUM' }, { label: 'futuresInviteCode', value: '416378774' }] },
    { name: 'okx', url: 'https://okx.com/join/A999998', codes: [{ label: 'inviteCode', value: 'A999998' }] },
  ] },
  { id: 'wallets', icon: WalletIcon, action: 'openWallet', providers: [
    { name: 'okx', url: 'https://web3.okx.com/ul/joindex?ref=1234567', codes: [{ label: 'inviteCode', value: '1234567' }] },
    { name: 'binance', url: 'https://web3.binance.com/referral?ref=RP3AEJ2M', codes: [{ label: 'inviteCode', value: 'RP3AEJ2M' }] },
  ] },
]
const resources = [
  { name: 'community', icon: ChatBubbleLeftRightIcon, url: 'https://t.me/CheshireBTC', address: 't.me/CheshireBTC' },
  { name: 'tutorial', icon: BookOpenIcon, url: 'https://0xcheshire.gitbook.io/web3/', address: '0xcheshire.gitbook.io/web3/' },
]
const copied = ref(''), copyError = ref(false)
let copyTimer: ReturnType<typeof setTimeout> | undefined
async function copyCode(code: string) {
  clearTimeout(copyTimer)
  copied.value = ''; copyError.value = false
  try {
    await navigator.clipboard.writeText(code)
    copied.value = code
    copyTimer = setTimeout(() => { copied.value = '' }, 2000)
  } catch { copyError.value = true }
}
onBeforeUnmount(() => clearTimeout(copyTimer))
</script>

<style scoped>
.referral-inner{max-width:1280px}
.referral-intro{margin-top:10px}
.referral-page section+section{padding-top:8px}
.referral-section-heading{display:flex;align-items:center;flex-wrap:wrap;gap:12px;margin-bottom:16px}
.referral-benefit{padding:4px 9px;border:1px solid color-mix(in srgb,var(--ui-favorite) 28%,var(--ui-border));border-radius:4px;font-size:12px;color:var(--ui-favorite);background:color-mix(in srgb,var(--ui-favorite) 8%,var(--ui-panel))}
.referral-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}
.referral-card{min-width:0;padding:20px 22px}
.referral-provider{display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap}
.referral-provider-name{display:flex;align-items:center;gap:12px}
h3{font-size:16px;font-weight:600;color:var(--ui-title)}
.referral-icon{display:inline-flex;align-items:center;justify-content:center;flex-shrink:0;width:40px;height:40px;border:1px solid var(--ui-border);border-radius:6px;background:var(--ui-toolbar);color:var(--ui-text)}
.referral-icon svg{width:22px;height:22px}
.referral-provider>a{padding:6px 12px;min-height:36px;font-size:13px}
.referral-provider>a svg{width:15px;height:15px}
.referral-codes{margin-top:20px;border-top:1px solid var(--ui-border);padding-top:8px}
.referral-codes>div{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px 16px;min-height:42px;padding-top:4px}
dt{color:var(--ui-muted);font-size:13px}
.referral-copy{display:inline-flex;align-items:center;gap:12px;min-height:36px;padding:4px 8px;margin-right:-8px;border-radius:4px;color:var(--ui-text)}
.referral-copy:hover{background:var(--ui-hover)}
.referral-copy code{font-size:14px;letter-spacing:.04em;color:var(--ui-title);user-select:text}
.referral-copy svg{width:16px;height:16px;color:var(--ui-muted)}
.referral-resource{display:flex;align-items:center;gap:14px;min-width:0;padding:20px 22px;transition:background 150ms,border-color 150ms}
.referral-resource:hover{background:var(--ui-toolbar);border-color:var(--ui-borderStrong)}
.referral-resource>div{flex:1;min-width:0}
.referral-resource p{margin-top:5px;font-size:12px;color:var(--ui-muted);overflow-wrap:anywhere}
.referral-resource-arrow{flex-shrink:0;width:18px;height:18px;color:var(--ui-muted)}
.referral-copy-error{font-size:13px;color:var(--ui-negative)}
@container app-content (max-width:48rem){.referral-grid{grid-template-columns:minmax(0,1fr)}}
@media(max-width:767px){.referral-card,.referral-resource{padding:18px}.referral-provider>a,.referral-copy{min-height:44px}.referral-page section+section{padding-top:0}}
@media(prefers-reduced-motion:reduce){.referral-resource{transition:none}}
</style>
