import colors from 'tailwindcss/colors.js'
import plugin from 'tailwindcss/plugin.js'
import { DARK_PALETTE, DARK_NEUTRALS, hexRgb } from './src/theme/palette.mjs'

const neutralColors = (family) => Object.fromEntries(
    Object.entries(colors[family]).map(([shade, value]) => [
        shade, `rgb(var(--ui-neutral-${shade}, ${hexRgb(value)}) / <alpha-value>)`,
    ]),
)

/** @type {import('tailwindcss').Config} */
export default {
    content: [
        "./index.html",
        "./src/**/*.{vue,js,ts,jsx,tsx}",
    ],
    darkMode: 'class',
    theme: {
        extend: {
            colors: {
                slate: neutralColors('slate'),
                gray: neutralColors('gray'),
                zinc: neutralColors('zinc'),
                neutral: neutralColors('neutral'),
                stone: neutralColors('stone'),
                'opentrading-dark': 'var(--app-bg, #0f172a)',
                'opentrading-panel': 'var(--app-surface, #1e293b)',
                'opentrading-accent': '#3b82f6',
            }
        },
    },
    plugins: [plugin(({ addBase }) => {
        addBase({
            'html.dark': {
                ...Object.fromEntries(Object.entries(DARK_NEUTRALS).map(([shade, value]) => [`--ui-neutral-${shade}`, hexRgb(value)])),
                ...Object.fromEntries(Object.entries(DARK_PALETTE).map(([key, value]) => [`--ui-${key}`, value])),
            },
        })
    })],
}
