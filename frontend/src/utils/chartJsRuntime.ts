import { Chart, registerables } from 'chart.js'
import annotationPlugin from 'chartjs-plugin-annotation'
import 'chartjs-adapter-date-fns'

// Cached pages keep their charts alive. Register shared plugins before any
// instance is created, so a later page cannot add an uninitialized plugin.
Chart.register(...registerables, annotationPlugin)

export { Chart }
