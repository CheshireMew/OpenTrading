<template>
  <div class="pine-editor" ref="host" @keydown.stop />
</template>
<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'
import * as monaco from 'monaco-editor/editor/editor.api.js'
import EditorWorker from 'monaco-editor/editor/editor.worker.js?worker'
const props=defineProps<{modelValue:string;dark:boolean;error?:{message:string;line?:number;column?:number}|null}>()
const emit=defineEmits<{ 'update:modelValue':[string]; run:[]; save:[] }>()
const host=ref<HTMLElement>()
let editor:monaco.editor.IStandaloneCodeEditor|undefined
let model:monaco.editor.ITextModel|undefined
let changing=false;
(self as typeof self & { MonacoEnvironment: monaco.Environment }).MonacoEnvironment={getWorker:()=>new EditorWorker()}
if(!monaco.languages.getLanguages().some(l=>l.id==='pine')) {
  monaco.languages.register({id:'pine',extensions:['.pine']})
  monaco.languages.setMonarchTokensProvider('pine',{tokenizer:{root:[
    [/\/\/.*$/,'comment'],[/"([^"\\]|\\.)*"|'([^'\\]|\\.)*'/,'string'],
    [/\b(if|else|for|while|switch|var|varip|true|false|na|and|or|not|break|continue|return|type|method|export)\b/,'keyword'],
    [/\b(indicator|strategy|plot|plotshape|fill|input|ta|math|request|label|line|box|table|array|color|barstate|syminfo)\b/,'type'],
    [/\b\d+(\.\d+)?\b/,'number'],[/[=:+\-*\/<>!]+/,'operator'],[/[a-zA-Z_]\w*/,'identifier'],
  ]}})
  monaco.languages.setLanguageConfiguration('pine',{comments:{lineComment:'//'},brackets:[['(',')'],['[',']']],autoClosingPairs:[{open:'(',close:')'},{open:'[',close:']'},{open:'"',close:'"'}]})
}
onMounted(()=>{
  model=monaco.editor.createModel(props.modelValue,'pine')
  editor=monaco.editor.create(host.value!,{model,theme:props.dark?'vs-dark':'vs',automaticLayout:true,minimap:{enabled:false},fontSize:13,tabSize:4,scrollBeyondLastLine:false,padding:{top:10},wordWrap:'off'})
  editor.onDidChangeModelContent(()=>{if(!changing)emit('update:modelValue',editor!.getValue())})
  editor.addCommand(monaco.KeyMod.CtrlCmd|monaco.KeyCode.Enter,()=>emit('run'))
  editor.addCommand(monaco.KeyMod.CtrlCmd|monaco.KeyCode.KeyS,()=>emit('save'))
})
watch(()=>props.modelValue,value=>{if(editor&&editor.getValue()!==value){changing=true;editor.setValue(value);changing=false}})
watch(()=>props.dark,value=>monaco.editor.setTheme(value?'vs-dark':'vs'))
watch(()=>props.error,error=>{
  if(model)monaco.editor.setModelMarkers(model,'pine',error?[{severity:monaco.MarkerSeverity.Error,message:error.message,
    startLineNumber:error.line??1,endLineNumber:error.line??1,startColumn:error.column??1,endColumn:(error.column??1)+1}]:[])
})
onBeforeUnmount(()=>{editor?.dispose();model?.dispose()})
</script>
<style scoped>.pine-editor{height:100%;min-height:80px;min-width:0;flex:1}</style>
