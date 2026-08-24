<template>
  <div class="editor-section">
    <div class="flex items-center justify-between gap-3">
      <div class="flex-1 space-y-2">
        <div class="section-title">{{ title || node.label }}</div>
        <input v-model="node.label" class="input" type="text" />
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <label class="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-300">
          <input v-model="node.enabled" type="checkbox" />
          <span>启用分组</span>
        </label>
        <select v-model="node.logic" class="input !w-[140px]">
          <option v-for="option in groupLogicOptions" :key="option.key" :value="option.key">{{ option.label }}</option>
        </select>
        <button class="btn-secondary px-3" @click="addCondition">添加条件</button>
        <button class="btn-secondary px-3" @click="addGroup">添加分组</button>
        <button v-if="removable" class="btn-danger" @click="$emit('remove')">删除分组</button>
      </div>
    </div>

    <div class="space-y-3">
      <div v-for="child in node.children" :key="child.id">
        <RuleTreeEditor
          v-if="child.node_type === 'group'"
          :node="child"
          :editor-contract="editorContract"
          :source-options="sourceOptions"
          :indicator-source-options="indicatorSourceOptions"
          :operator-options="operatorOptions"
          :group-logic-options="groupLogicOptions"
          :title="child.label"
          removable
          @remove="removeChild(child.id)"
        />
        <div v-else class="editor-card space-y-3">
          <div class="flex items-center justify-between gap-3">
            <input v-model="child.label" class="input" type="text" />
            <div class="flex items-center gap-2">
              <label class="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-300">
                <input v-model="child.enabled" type="checkbox" />
                <span>启用</span>
              </label>
              <button class="btn-danger" @click="removeChild(child.id)">删除</button>
            </div>
          </div>
          <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div>
              <label class="label">左侧来源</label>
              <select :value="encodeSource(child.left)" class="input" @change="updateRuleSource(child, 'left', $event.target.value)">
                <option v-for="option in sourceOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
              </select>
            </div>
            <div>
              <label class="label">操作符</label>
              <select v-model="child.operator" class="input">
                <option v-for="option in operatorOptions" :key="option.key" :value="option.key">{{ option.label }}</option>
              </select>
            </div>
            <div>
              <label class="label">右侧类型</label>
              <select :value="child.right.kind" class="input" @change="changeRightKind(child, $event.target.value)">
                <option value="value">固定数值</option>
                <option value="indicator">指标来源</option>
                <option value="indicator_multiplier">指标乘数</option>
                <option value="indicator_offset">偏移公式</option>
              </select>
            </div>
          </div>
          <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
            <template v-if="child.right.kind === 'value'">
              <div>
                <label class="label">固定数值</label>
                <input v-model.number="child.right.value" class="input" type="number" step="0.1" />
              </div>
            </template>
            <template v-else-if="child.right.kind === 'indicator'">
              <div class="md:col-span-2">
                <label class="label">右侧来源</label>
                <select :value="encodeSource(child.right)" class="input" @change="updateRuleSource(child, 'right', $event.target.value)">
                  <option v-for="option in indicatorSourceOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
                </select>
              </div>
            </template>
            <template v-else-if="child.right.kind === 'indicator_multiplier'">
              <div class="md:col-span-2">
                <label class="label">右侧来源</label>
                <select :value="encodeMultiplierSource(child.right)" class="input" @change="updateMultiplierSource(child, $event.target.value)">
                  <option v-for="option in indicatorSourceOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
                </select>
              </div>
              <div>
                <label class="label">乘数</label>
                <input v-model.number="child.right.multiplier" class="input" type="number" step="0.1" />
              </div>
            </template>
            <template v-else-if="child.right.kind === 'indicator_offset'">
              <div>
                <label class="label">基准来源</label>
                <select :value="encodeOffsetSource(child.right, 'base')" class="input" @change="updateOffsetSource(child, 'base', $event.target.value)">
                  <option v-for="option in indicatorSourceOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
                </select>
              </div>
              <div>
                <label class="label">偏移来源</label>
                <select :value="encodeOffsetSource(child.right, 'offset')" class="input" @change="updateOffsetSource(child, 'offset', $event.target.value)">
                  <option v-for="option in indicatorSourceOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
                </select>
              </div>
              <div>
                <label class="label">乘数</label>
                <input v-model.number="child.right.offset_multiplier" class="input" type="number" step="0.1" />
              </div>
            </template>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { buildId, createBlankCondition, createBlankGroup } from '@/modules/backtest/editorContract'

defineOptions({ name: 'RuleTreeEditor' })

const props = defineProps({
  node: { type: Object, required: true },
  editorContract: { type: Object, required: true },
  title: { type: String, default: '' },
  removable: { type: Boolean, default: false },
  sourceOptions: { type: Array, default: () => [] },
  indicatorSourceOptions: { type: Array, default: () => [] },
  operatorOptions: { type: Array, default: () => [] },
  groupLogicOptions: { type: Array, default: () => [] },
})

defineEmits(['remove'])

const encodeSource = (source) => {
  if (!source) return ''
  const barsAgo = Number(source.bars_ago ?? 0)
  if (source.kind === 'price') return `price:${source.field}:${barsAgo}`
  if (source.kind === 'indicator') return `indicator:${source.indicator}:${source.output}:${barsAgo}`
  return ''
}

const decodeSource = (value) => {
  const [kind, partA, partB, partC] = String(value || '').split(':')
  if (kind === 'price') return { kind: 'price', field: partA, bars_ago: Number(partB || 0) }
  if (kind === 'indicator') return { kind: 'indicator', indicator: partA, output: partB || 'value', bars_ago: Number(partC || 0) }
  return { kind: 'price', field: 'close', bars_ago: 0 }
}

const encodeMultiplierSource = (source) => `indicator:${source?.indicator || ''}:${source?.output || 'value'}:${Number(source?.bars_ago ?? 0)}`
const encodeOffsetSource = (source, side) => {
  if (side === 'base') return `indicator:${source?.base_indicator || ''}:${source?.base_output || 'value'}:${Number(source?.bars_ago ?? 0)}`
  return `indicator:${source?.offset_indicator || ''}:${source?.offset_output || 'value'}:${Number(source?.bars_ago ?? 0)}`
}

const updateRuleSource = (rule, side, value) => {
  rule[side] = decodeSource(value)
}

const updateMultiplierSource = (rule, value) => {
  const parsed = decodeSource(value)
  rule.right = {
    kind: 'indicator_multiplier',
    indicator: parsed.indicator,
    output: parsed.output,
    bars_ago: Number(parsed.bars_ago ?? 0),
    multiplier: Number(rule.right.multiplier ?? 1.5),
  }
}

const updateOffsetSource = (rule, side, value) => {
  const parsed = decodeSource(value)
  const next = {
    kind: 'indicator_offset',
    base_indicator: rule.right.base_indicator,
    base_output: rule.right.base_output,
    offset_indicator: rule.right.offset_indicator,
    offset_output: rule.right.offset_output,
    bars_ago: Number(rule.right.bars_ago ?? 0),
    offset_multiplier: Number(rule.right.offset_multiplier ?? 1),
  }
  if (side === 'base') {
    next.base_indicator = parsed.indicator
    next.base_output = parsed.output
    next.bars_ago = Number(parsed.bars_ago ?? 0)
  } else {
    next.offset_indicator = parsed.indicator
    next.offset_output = parsed.output
    next.bars_ago = Number(parsed.bars_ago ?? 0)
  }
  rule.right = next
}

const changeRightKind = (rule, kind) => {
  const firstIndicator = props.indicatorSourceOptions[0]?.value || 'indicator:ema:value'
  if (kind === 'value') {
    rule.right = { kind: 'value', value: 0 }
    return
  }
  if (kind === 'indicator') {
    rule.right = decodeSource(firstIndicator)
    return
  }
  if (kind === 'indicator_multiplier') {
    const parsed = decodeSource(firstIndicator)
    rule.right = { kind: 'indicator_multiplier', indicator: parsed.indicator, output: parsed.output, bars_ago: Number(parsed.bars_ago ?? 0), multiplier: 1.5 }
    return
  }
  const parsed = decodeSource(firstIndicator)
  rule.right = {
    kind: 'indicator_offset',
    base_indicator: parsed.indicator,
    base_output: parsed.output,
    offset_indicator: parsed.indicator,
    offset_output: parsed.output,
    bars_ago: Number(parsed.bars_ago ?? 0),
    offset_multiplier: 1,
  }
}

const addCondition = () => {
  const source = props.indicatorSourceOptions[0] ? decodeSource(props.indicatorSourceOptions[0].value) : { kind: 'price', field: 'close' }
  props.node.children.push(createBlankCondition(props.editorContract, {
    id: buildId('rule'),
    label: '新条件',
    right: source.kind === 'indicator' ? source : { kind: 'value', value: 0 },
  }))
}

const addGroup = () => {
  props.node.children.push(createBlankGroup(props.editorContract, {
    id: buildId('group'),
    label: '新分组',
    logic: 'and',
    children: [],
  }))
}

const removeChild = (childId) => {
  const index = props.node.children.findIndex((child) => child.id === childId)
  if (index >= 0) props.node.children.splice(index, 1)
}
</script>

