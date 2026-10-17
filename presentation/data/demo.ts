import { parse } from 'yaml'
import questionsYaml from '../../src/lgh/laya/questions_v0_1.yaml?raw'
import metricsJson from './metrics.json'
import recordedJson from './recorded.json'

// Question set the daemon is asked, read from the same file LGH uses.
export interface QuestionDefinition {
  type: 'choice' | 'noul'
  instructions: string
  criteria?: Record<string, string>
}

export const questions: Record<string, QuestionDefinition> = parse(questionsYaml)
export const questionKeys = Object.keys(questions)

// Swedish slide labels for the seven questions.
export const questionLabels: Record<string, string> = {
  task_alignment: 'Hör handlingen till uppgiften?',
  destructive_risk: 'Kan den förstöra data?',
  sensitive_resource: 'Rör den hemligheter eller behörighet?',
  external_impact: 'Påverkar den något utanför repot?',
  reversibility: 'Hur lätt kan den ångras?',
  verification_needed: 'Behövs extra kontroll först?',
  handling: 'Hur ska den hanteras?',
}

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

export interface LayaState {
  goal: string
  plan?: string
  repo: { branch?: string, dirty: boolean, changed: string[] }
  environment: string
  action: { tool: string, operation: string, command?: string, target?: string }
  recent: string[]
}

export interface ModelRun {
  answers: Answers
  latency_ms: number
  input_tokens: number
  decision: string
}

export interface Preset {
  state: LayaState
  base: ModelRun
  fine_tuned: ModelRun
}

export interface SequenceLayout {
  tokens: number
  head: number
  options: number
  markers: number
  state: number
  pieces: string[]
  marker_positions: number[]
}

interface Recorded {
  recorded_at: string
  device: string
  runs_per_measurement: number
  presets: Record<string, Preset>
  layout: Record<string, SequenceLayout>
}

export const recorded = recordedJson as Recorded
export const presets = recorded.presets
export const deleteExample = presets.delete

// Aggregates from scripts/collect_metrics.py.
export const metrics = metricsJson

/** Probability of the label Laya picked, as LGH's reducer reads it (lgh/laya/normalize.py). */
export function chosenProbability(answer: ChoiceAnswer): number {
  return answer.probabilities[answer.choice]
}

const number = new Intl.NumberFormat('sv-SE')
const decimal = new Intl.NumberFormat('sv-SE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

export function formatCount(value: number): string {
  return number.format(value)
}

export function formatProbability(value: number): string {
  return decimal.format(value)
}

export function formatMs(value: number): string {
  return `${number.format(Math.round(value))} ms`
}
