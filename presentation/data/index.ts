import metricsJson from './metrics.json'
import recordedJson from './recorded.json'

export interface ChoiceAnswer {
  type: 'choice'
  choice: string
  probabilities: Record<string, number>
  confidence: number
}

export interface NoulAnswer {
  type: 'noul'
  noul: number
  confidence: number
}

export type Answer = ChoiceAnswer | NoulAnswer
export type Answers = Record<string, Answer>

export interface Question {
  type: 'choice' | 'noul'
  instructions: string
  criteria?: Record<string, string>
}

export interface LayaRun {
  answers: Answers
  input_tokens: number
  output_tokens: number
  latency_ms: number
}

export interface LlmRun {
  chunks: { t_ms: number, text: string }[]
  text: string
  total_ms: number
  first_token_ms: number
  output_tokens: number
  input_tokens: number
  model: string
}

export interface Recorded {
  recorded_at: string
  device: string
  states: Record<string, Record<string, unknown>>
  questions: Record<string, Question>
  laya: Record<'base' | 'fine_tuned', { model: string, parameters: number, states: Record<string, LayaRun>, handling_layout: string[] }>
  llm: Record<string, LlmRun>
  pipeline: Record<string, { rules: string[], rule_disposition: string, decision: Record<'base' | 'fine_tuned', string> }>
}

export const recorded = recordedJson as unknown as Recorded
export const metrics = metricsJson

export const SCENARIOS: Record<string, string> = {
  ls: 'ls src/app',
  rm: 'rm -rf build/',
  push: 'git push --force origin main',
  env: 'cat .env',
}

export const QUESTION_LABELS: Record<string, string> = {
  task_alignment: 'Hör till uppgiften?',
  destructive_risk: 'Förstörande?',
  sensitive_resource: 'Känslig resurs?',
  external_impact: 'Påverkar externt?',
  reversibility: 'Går att ångra?',
  verification_needed: 'Behöver kontroll?',
  handling: 'Hantering',
}

const sv = new Intl.NumberFormat('sv-SE', { maximumFractionDigits: 1 })
const svInt = new Intl.NumberFormat('sv-SE', { maximumFractionDigits: 0 })

export function formatNumber(value: number, digits = 0): string {
  return new Intl.NumberFormat('sv-SE', { maximumFractionDigits: digits, minimumFractionDigits: digits }).format(value)
}

export function formatPercent(value: number): string {
  return `${svInt.format(value * 100)} %`
}

export function formatMs(ms: number): string {
  return ms >= 1000 ? `${sv.format(ms / 1000)} s` : `${svInt.format(ms)} ms`
}

function average(values: number[]): number {
  return values.reduce((sum, value) => sum + value, 0) / values.length
}

export const layaMeanMs = average(Object.values(recorded.laya.fine_tuned.states).map(run => run.latency_ms))
export const llmMeanMs = average(Object.values(recorded.llm).map(run => run.total_ms))
export const llmFirstTokenMeanMs = average(Object.values(recorded.llm).map(run => run.first_token_ms))
export const speedup = llmMeanMs / layaMeanMs
