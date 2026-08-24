import { useCallback, useEffect, useState } from "react"
import {
  BookOpenCheck,
  BrainCircuit,
  CheckCircle2,
  KeyRound,
  LoaderCircle,
  RefreshCw,
  Save,
  Sparkles,
  TestTube2,
} from "lucide-react"

import { Alert } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  listAiConfigs,
  listAiModels,
  testAiConfig,
  updateAiConfig,
} from "@/lib/api"
import type { AiConfig, AiConfigPurpose } from "@/types"

const deepseekApiBase = "https://api.deepseek.com"
const fallbackModels = ["deepseek-chat", "deepseek-reasoner"]

const purposeMeta = {
  realtime: {
    title: "AI 实时分析",
    description: "用于实时盯播诊断、行动建议和直播结束后的整场复盘。",
    icon: BrainCircuit,
  },
  corpus: {
    title: "整理语料库",
    description: "用于提炼上传文件、去重压缩并生成固定结构的 Markdown 语料。",
    icon: BookOpenCheck,
  },
} as const

interface FormState {
  apiKey: string
  model: string
  hasApiKey: boolean
  configured: boolean
  source: "admin" | "environment"
  models: string[]
  saving: boolean
  testing: boolean
  loadingModels: boolean
  message: string | null
  error: string | null
}

function initialForm(): FormState {
  return {
    apiKey: "",
    model: "deepseek-chat",
    hasApiKey: false,
    configured: false,
    source: "environment",
    models: fallbackModels,
    saving: false,
    testing: false,
    loadingModels: false,
    message: null,
    error: null,
  }
}

export function AdminAiConfig() {
  const [forms, setForms] = useState<Record<AiConfigPurpose, FormState>>({
    realtime: initialForm(),
    corpus: initialForm(),
  })
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  const patchForm = useCallback(
    (purpose: AiConfigPurpose, patch: Partial<FormState>) => {
      setForms((current) => ({
        ...current,
        [purpose]: { ...current[purpose], ...patch },
      }))
    },
    [],
  )

  const applyConfig = useCallback((config: AiConfig) => {
    setForms((current) => ({
      ...current,
      [config.purpose]: {
        ...current[config.purpose],
        apiKey: "",
        model: config.model || "deepseek-chat",
        hasApiKey: config.has_api_key,
        configured: config.configured,
        source: config.source,
      },
    }))
  }, [])

  const loadConfigs = useCallback(async () => {
    setLoading(true)
    try {
      const configs = await listAiConfigs()
      configs.forEach(applyConfig)
      setLoadError(null)
    } catch (caught) {
      setLoadError(caught instanceof Error ? caught.message : "AI 配置加载失败")
    } finally {
      setLoading(false)
    }
  }, [applyConfig])

  useEffect(() => {
    void loadConfigs()
  }, [loadConfigs])

  async function refreshModels(purpose: AiConfigPurpose) {
    const form = forms[purpose]
    patchForm(purpose, { loadingModels: true, error: null, message: null })
    try {
      const result = await listAiModels(purpose, {
        api_base: deepseekApiBase,
        api_key: form.apiKey || undefined,
        model: form.model,
      })
      const models = result.models.length > 0 ? result.models : fallbackModels
      patchForm(purpose, {
        models,
        model: models.includes(form.model) ? form.model : models[0],
        message: `已获取 ${models.length} 个 DeepSeek 模型`,
      })
    } catch (caught) {
      patchForm(purpose, {
        error: caught instanceof Error ? caught.message : "模型列表获取失败",
      })
    } finally {
      patchForm(purpose, { loadingModels: false })
    }
  }

  async function testConnection(purpose: AiConfigPurpose) {
    const form = forms[purpose]
    patchForm(purpose, { testing: true, error: null, message: null })
    try {
      const result = await testAiConfig(purpose, {
        api_base: deepseekApiBase,
        api_key: form.apiKey || undefined,
        model: form.model,
      })
      patchForm(purpose, { message: result.message })
    } catch (caught) {
      patchForm(purpose, {
        error: caught instanceof Error ? caught.message : "连接测试失败",
      })
    } finally {
      patchForm(purpose, { testing: false })
    }
  }

  async function saveConfig(purpose: AiConfigPurpose) {
    const form = forms[purpose]
    patchForm(purpose, { saving: true, error: null, message: null })
    try {
      const saved = await updateAiConfig(purpose, {
        api_base: deepseekApiBase,
        api_key: form.apiKey || undefined,
        model: form.model,
      })
      applyConfig(saved)
      patchForm(purpose, { message: "配置已保存，所有账号的新任务将立即使用" })
    } catch (caught) {
      patchForm(purpose, {
        error: caught instanceof Error ? caught.message : "配置保存失败",
      })
    } finally {
      patchForm(purpose, { saving: false })
    }
  }

  return (
    <Card className="bg-card/90">
      <CardHeader className="border-b border-border/60">
        <CardTitle className="flex items-center gap-2">
          <Sparkles className="size-4 text-primary" />
          AI 配置中心
        </CardTitle>
        <CardDescription>
          管理员统一配置 DeepSeek。API Key 不会回显，保存后所有启用账号立即共享。
        </CardDescription>
      </CardHeader>
      <CardContent>
        {loadError && (
          <Alert className="mb-4 border-destructive/30 bg-destructive/5 text-destructive">
            {loadError}
          </Alert>
        )}
        {loading ? (
          <div className="grid gap-4 lg:grid-cols-2">
            {[0, 1].map((item) => (
              <div key={item} className="h-96 animate-pulse rounded-xl bg-muted" />
            ))}
          </div>
        ) : (
          <div className="grid items-start gap-4 lg:grid-cols-2">
            {(["realtime", "corpus"] as const).map((purpose) => (
              <AiConfigForm
                key={purpose}
                purpose={purpose}
                form={forms[purpose]}
                onPatch={(patch) => patchForm(purpose, patch)}
                onRefreshModels={() => void refreshModels(purpose)}
                onTest={() => void testConnection(purpose)}
                onSave={() => void saveConfig(purpose)}
              />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function AiConfigForm({
  purpose,
  form,
  onPatch,
  onRefreshModels,
  onTest,
  onSave,
}: {
  purpose: AiConfigPurpose
  form: FormState
  onPatch: (patch: Partial<FormState>) => void
  onRefreshModels: () => void
  onTest: () => void
  onSave: () => void
}) {
  const meta = purposeMeta[purpose]
  const Icon = meta.icon
  const busy = form.saving || form.testing || form.loadingModels
  const canUseStoredKey = form.hasApiKey && !form.apiKey

  return (
    <section className="grid gap-4 rounded-xl border border-border/70 bg-background/45 p-4" aria-labelledby={`ai-config-${purpose}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Icon className="size-5" />
          </div>
          <div className="min-w-0">
            <h3 id={`ai-config-${purpose}`} className="text-sm font-semibold">{meta.title}</h3>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">{meta.description}</p>
          </div>
        </div>
        <Badge variant={form.configured ? "success" : "warning"}>
          {form.configured ? "已配置" : "待配置"}
        </Badge>
      </div>

      <div className="grid gap-2">
        <Label>服务商</Label>
        <div className="flex h-10 items-center justify-between rounded-lg border border-input bg-card px-3 text-sm">
          <span className="font-medium">DeepSeek</span>
          <span className="truncate text-xs text-muted-foreground">api.deepseek.com</span>
        </div>
      </div>

      <div className="grid gap-2">
        <Label htmlFor={`ai-key-${purpose}`}>API Key</Label>
        <div className="relative">
          <KeyRound className="pointer-events-none absolute left-3 top-3 size-4 text-muted-foreground" />
          <Input
            id={`ai-key-${purpose}`}
            type="password"
            autoComplete="new-password"
            value={form.apiKey}
            onChange={(event) => onPatch({ apiKey: event.target.value, error: null, message: null })}
            placeholder={form.hasApiKey ? "已安全保存；留空则保持不变" : "sk-..."}
            className="pl-9"
          />
        </div>
        <p className="text-[11px] leading-5 text-muted-foreground">
          {form.source === "admin" ? "使用管理员配置的加密密钥" : "当前继承服务端环境配置"}；界面和接口均不会返回原始密钥。
        </p>
      </div>

      <div className="grid gap-2">
        <div className="flex items-center justify-between gap-2">
          <Label htmlFor={`ai-model-${purpose}`}>模型</Label>
          <Button type="button" variant="ghost" size="sm" disabled={busy || (!form.apiKey && !form.hasApiKey)} onClick={onRefreshModels}>
            {form.loadingModels ? <LoaderCircle data-icon="inline-start" className="animate-spin" /> : <RefreshCw data-icon="inline-start" />}
            刷新模型
          </Button>
        </div>
        <select
          id={`ai-model-${purpose}`}
          value={form.model}
          onChange={(event) => onPatch({ model: event.target.value, error: null, message: null })}
          className="h-10 rounded-lg border border-input bg-card px-3 text-sm outline-none transition-[border-color,box-shadow] focus-visible:border-primary/50 focus-visible:ring-3 focus-visible:ring-ring/15"
        >
          {Array.from(new Set([...form.models, form.model])).filter(Boolean).map((model) => (
            <option key={model} value={model}>{model}</option>
          ))}
        </select>
      </div>

      {form.error && <Alert className="border-destructive/30 bg-destructive/5 text-destructive">{form.error}</Alert>}
      {form.message && (
        <Alert className="flex items-start gap-2 border-success/25 bg-success/5 text-success">
          <CheckCircle2 className="mt-1 size-4 shrink-0" />
          <span>{form.message}</span>
        </Alert>
      )}

      <div className="flex flex-wrap gap-2 border-t border-border/60 pt-4">
        <Button type="button" variant="outline" disabled={busy || (!form.apiKey && !form.hasApiKey)} onClick={onTest}>
          {form.testing ? <LoaderCircle data-icon="inline-start" className="animate-spin" /> : <TestTube2 data-icon="inline-start" />}
          测试连接
        </Button>
        <Button type="button" disabled={busy || !form.model || (!form.apiKey && !form.hasApiKey)} onClick={onSave}>
          {form.saving ? <LoaderCircle data-icon="inline-start" className="animate-spin" /> : <Save data-icon="inline-start" />}
          保存并应用
        </Button>
      </div>
      {canUseStoredKey && <span className="sr-only">已存在可用的 API Key</span>}
    </section>
  )
}
