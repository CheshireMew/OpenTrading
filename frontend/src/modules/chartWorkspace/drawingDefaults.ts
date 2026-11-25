import { drawingTypes, registerDrawingType, type DrawingStyle } from '@luxalgo/vela'

const LINE_GROUPS = new Set(['lines', 'channels', 'pitchforks'])
const SHAPES = new Set(['arrow', 'box', 'ellipse', 'triangle', 'polyline', 'freehand', 'circle', 'rotatedrect', 'path', 'arc', 'curve'])
const DRAWING_GRAY = '#787878'

export function registerWorkspaceDrawingDefaults() {
  for (const definition of drawingTypes()) {
    const line = LINE_GROUPS.has(definition.group) || definition.type === 'arrow'
    if (!line && !SHAPES.has(definition.type)) continue
    const defaultStyle: DrawingStyle = {
      ...definition.defaultStyle,
      lineColor: DRAWING_GRAY,
      lineWidth: 1,
      lineStyle: line ? 'dashed' : 'solid',
      ...(definition.defaultStyle.fillColor ? { fillColor: `${DRAWING_GRAY}14` } : {}),
    }
    // Seed the factory, including placement previews and "Reset settings".
    // The SDK still merges the user's last-used style and explicit overrides
    // over this seed, and deserializes existing drawings with their own styles.
    registerDrawingType({ ...definition, defaultStyle })
  }
}
