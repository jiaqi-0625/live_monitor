import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type DragEvent,
  type FormEvent,
} from "react"
import {
  BookOpenText,
  CheckCircle2,
  FileText,
  LoaderCircle,
  Pencil,
  Plus,
  Save,
  Trash2,
  UploadCloud,
  X,
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
import { Textarea } from "@/components/ui/textarea"
import {
  createCorpusEntry,
  deleteCorpusEntry,
  importCorpusFiles,
  listCorpus,
  updateCorpusEntry,
  type CorpusImportProgress,
} from "@/lib/api"
import { formatDateTime } from "@/lib/utils"
import type { CorpusEntry } from "@/types"

type CategoryOption = readonly [value: string, label: string]

const categoryGroups = [
  {
    label: "业务资料",
    options: [
      ["brand", "品牌口径"],
      ["vehicle", "车型卖点"],
      ["campaign", "活动政策"],
      ["script", "标准话术"],
      ["constraint", "禁用与约束"],
    ],
  },
  {
    label: "监控数据策略",
    options: [
      ["metric_core", "核心指标目标"],
      ["metric_traffic", "流量与观看"],
      ["metric_conversion", "转化与经营"],
      ["metric_engagement", "互动表现"],
      ["metric_threshold", "指标阈值与预警"],
    ],
  },
  {
    label: "其他",
    options: [["other", "其他资料"]],
  },
] as const satisfies ReadonlyArray<{
  label: string
  options: readonly CategoryOption[]
}>

const categories = categoryGroups.flatMap<CategoryOption>((group) =>
  Array.from<CategoryOption>(group.options),
)

const acceptedFileTypes = ".txt,.md,.markdown,.csv,.json,.html,.htm,.pdf,.docx,.xlsx,.pptx"
const acceptedExtensions = new Set(acceptedFileTypes.split(","))
const maxFileBytes = 10 * 1024 * 1024

interface CorpusLibraryProps {
  operatorName: string
}

export function CorpusLibraryView({ operatorName }: CorpusLibraryProps) {
  const [entries, setEntries] = useState<CorpusEntry[]>([])
  const [editingId, setEditingId] = useState<number | null>(null)
  const [category, setCategory] = useState("vehicle")
  const [title, setTitle] = useState("")
  const [content, setContent] = useState("")
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [mode, setMode] = useState<"file" | "manual">("file")
  const [selectedFiles, setSelectedFiles] = useState<File[]>([])
  const [dragging, setDragging] = useState(false)
  const [importing, setImporting] = useState(false)
  const [importProgress, setImportProgress] = useState<CorpusImportProgress | null>(null)
  const [importMessage, setImportMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const loadEntries = useCallback(async () => {
    try {
      setEntries(await listCorpus(operatorName))
      setError(null)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "语料库加载失败")
    } finally {
      setLoading(false)
    }
  }, [operatorName])

  useEffect(() => {
    setLoading(true)
    void loadEntries()
  }, [loadEntries])

  function resetForm() {
    setEditingId(null)
    setCategory("vehicle")
    setTitle("")
    setContent("")
  }

  function beginEdit(entry: CorpusEntry) {
    setMode("manual")
    setEditingId(entry.id)
    setCategory(entry.category)
    setTitle(entry.title)
    setContent(entry.content)
  }

  function addFiles(files: File[]) {
    setError(null)
    setImportMessage(null)
    const invalid = files.find((file) => {
      const extension = `.${file.name.split(".").pop()?.toLowerCase() ?? ""}`
      return !acceptedExtensions.has(extension) || file.size > maxFileBytes
    })
    if (invalid) {
      setError(`“${invalid.name}”格式不受支持或超过 10 MB`)
      return
    }
    const merged = [...selectedFiles]
    for (const file of files) {
      if (!merged.some((item) => item.name === file.name && item.size === file.size)) {
        merged.push(file)
      }
    }
    if (merged.length > 10) {
      setError("单次最多选择 10 个文件")
      return
    }
    setSelectedFiles(merged)
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    setDragging(false)
    addFiles(Array.from(event.dataTransfer.files))
  }

  async function handleImport() {
    if (selectedFiles.length === 0) return
    setImporting(true)
    setImportProgress({ phase: "uploading", percent: 0 })
    setError(null)
    setImportMessage(null)
    try {
      const result = await importCorpusFiles(
        operatorName,
        category,
        selectedFiles,
        setImportProgress,
      )
      const failedMessage = result.failures
        .map((item) => `${item.filename}：${item.error}`)
        .join("；")
      if (result.imported_files > 0) {
        const reduction = result.original_chars > 0
          ? Math.max(0, Math.round((1 - result.saved_chars / result.original_chars) * 100))
          : 0
        const optimizationMessage = result.fallback_files.length === result.imported_files
          ? "，模型未返回正文，已按原文入库"
          : `，内容精简约 ${reduction}%${result.fallback_files.length ? `；另有 ${result.fallback_files.length} 个文件按原文入库` : ""}`
        setImportMessage(
          `已导入 ${result.imported_files} 个文件，生成 ${result.imported_entries} 条 Markdown 语料${optimizationMessage}${failedMessage ? `；未导入：${failedMessage}` : ""}`,
        )
        setSelectedFiles([])
        if (fileInputRef.current) fileInputRef.current.value = ""
        await loadEntries()
      } else {
        setError(failedMessage || "文件导入失败")
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "文件导入失败")
    } finally {
      setImporting(false)
      setImportProgress(null)
    }
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setSaving(true)
    setError(null)
    try {
      const payload = {
        operator_name: operatorName,
        category,
        title: title.trim(),
        content: content.trim(),
      }
      if (editingId === null) await createCorpusEntry(payload)
      else await updateCorpusEntry(editingId, payload)
      resetForm()
      await loadEntries()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "语料保存失败")
    } finally {
      setSaving(false)
    }
  }

  async function toggleEntry(entry: CorpusEntry) {
    try {
      await updateCorpusEntry(entry.id, {
        operator_name: operatorName,
        enabled: !entry.enabled,
      })
      await loadEntries()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "语料状态更新失败")
    }
  }

  async function removeEntry(entry: CorpusEntry) {
    if (!window.confirm(`确定删除语料“${entry.title}”吗？删除后无法恢复。`)) return
    try {
      await deleteCorpusEntry(entry.id, operatorName)
      if (editingId === entry.id) resetForm()
      await loadEntries()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "语料删除失败")
    }
  }

  const enabledCount = entries.filter((entry) => entry.enabled).length

  return (
    <section className="grid gap-6" aria-labelledby="corpus-library-title">
      <div>
        <div className="mb-2 flex items-center gap-2 text-xs font-medium text-primary">
          <span className="size-1.5 rounded-full bg-primary" />
          KNOWLEDGE BASE
        </div>
        <h1 id="corpus-library-title" className="text-2xl font-semibold tracking-[-0.025em]">
          我的个性化语料库
        </h1>
        <p className="mt-1.5 text-sm text-muted-foreground">
          当前工作台：{operatorName}。已启用 {enabledCount}/{entries.length} 条语料，AI实时提醒会优先遵循这些内容。
        </p>
      </div>

      {error && <Alert className="text-destructive">{error}</Alert>}

      <div className="grid items-start gap-5 xl:grid-cols-[minmax(320px,0.8fr)_minmax(0,1.4fr)]">
        <Card className="bg-card/90 xl:sticky xl:top-24">
          <CardHeader className="border-b border-border/60">
            <CardTitle>{editingId === null ? "新增语料" : "编辑语料"}</CardTitle>
            <CardDescription>
              上传本地资料快速建库，也可以手动录入一条精准口径。
            </CardDescription>
          </CardHeader>
          <CardContent>
            {editingId === null && (
              <div className="mb-5 grid grid-cols-2 gap-1 rounded-lg bg-muted p-1" aria-label="语料添加方式">
                <Button
                  type="button"
                  size="sm"
                  variant={mode === "file" ? "outline" : "ghost"}
                  className={mode === "file" ? "bg-card" : undefined}
                  aria-pressed={mode === "file"}
                  onClick={() => setMode("file")}
                >
                  <UploadCloud data-icon="inline-start" />
                  文件导入
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant={mode === "manual" ? "outline" : "ghost"}
                  className={mode === "manual" ? "bg-card" : undefined}
                  aria-pressed={mode === "manual"}
                  onClick={() => setMode("manual")}
                >
                  <Plus data-icon="inline-start" />
                  手动录入
                </Button>
              </div>
            )}

            {mode === "file" && editingId === null ? (
              <div className="grid gap-4">
                <div className="grid gap-2">
                  <Label htmlFor="corpus-import-category">导入分类</Label>
                  <select
                    id="corpus-import-category"
                    value={category}
                    onChange={(event) => setCategory(event.target.value)}
                    className="h-10 rounded-lg border border-input bg-card px-3 text-sm outline-none transition-[border-color,box-shadow] focus-visible:border-primary/50 focus-visible:ring-3 focus-visible:ring-ring/15"
                  >
                    {categoryGroups.map((group) => (
                      <optgroup key={group.label} label={group.label}>
                        {group.options.map(([value, label]) => (
                          <option key={value} value={value}>{label}</option>
                        ))}
                      </optgroup>
                    ))}
                  </select>
                </div>
                <div
                  className={`grid min-h-44 cursor-pointer place-items-center rounded-xl border border-dashed p-5 text-center outline-none transition-[border-color,background-color,box-shadow] focus-visible:ring-2 focus-visible:ring-ring/60 ${dragging ? "border-primary bg-primary/5" : "border-input bg-background/45 hover:border-primary/40 hover:bg-accent/40"}`}
                  role="button"
                  tabIndex={0}
                  onClick={() => fileInputRef.current?.click()}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault()
                      fileInputRef.current?.click()
                    }
                  }}
                  onDragEnter={(event) => { event.preventDefault(); setDragging(true) }}
                  onDragOver={(event) => event.preventDefault()}
                  onDragLeave={() => setDragging(false)}
                  onDrop={handleDrop}
                >
                  <div>
                    <UploadCloud className="mx-auto size-9 text-primary" />
                    <p className="mt-3 text-sm font-medium">点击选择或拖拽文件到这里</p>
                    <p className="mt-1 text-xs leading-5 text-muted-foreground">
                      TXT、Markdown、CSV、JSON、HTML、PDF、Word、Excel、PPT<br />
                      单个最大 10 MB，一次最多 10 个
                    </p>
                    <p className="mt-2 text-xs font-medium text-primary">
                      AI 将提炼去重并统一为 Markdown 后入库
                    </p>
                  </div>
                  <input
                    ref={fileInputRef}
                    className="sr-only"
                    type="file"
                    multiple
                    accept={acceptedFileTypes}
                    onChange={(event) => addFiles(Array.from(event.target.files ?? []))}
                  />
                </div>
                {selectedFiles.length > 0 && (
                  <div className="grid gap-2" aria-live="polite">
                    {selectedFiles.map((file) => (
                      <div key={`${file.name}-${file.size}`} className="flex items-center gap-3 rounded-lg border border-border/70 bg-background/45 px-3 py-2.5">
                        <FileText className="size-4 shrink-0 text-primary" />
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-xs font-medium">{file.name}</p>
                          <p className="text-[11px] text-muted-foreground">{formatFileSize(file.size)}</p>
                        </div>
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          className="size-8"
                          aria-label={`移除 ${file.name}`}
                          onClick={(event) => {
                            event.stopPropagation()
                            setSelectedFiles((items) => items.filter((item) => item !== file))
                          }}
                        >
                          <X />
                        </Button>
                      </div>
                    ))}
                  </div>
                )}
                <Button type="button" disabled={importing || selectedFiles.length === 0} onClick={() => void handleImport()}>
                  {importing ? <LoaderCircle data-icon="inline-start" className="animate-spin" /> : <UploadCloud data-icon="inline-start" />}
                  {importing
                    ? importProgress?.phase === "processing"
                      ? "AI 正在解析并导入"
                      : `正在上传${importProgress?.percent === null || importProgress?.percent === undefined ? "" : ` ${importProgress.percent}%`}`
                    : `导入${selectedFiles.length ? ` ${selectedFiles.length} 个` : ""}文件`}
                </Button>
                {importing && (
                  <Alert
                    className="flex items-start gap-3 rounded-xl border border-primary/20 bg-primary/5 px-4 py-3 text-sm"
                    role="status"
                    aria-live="polite"
                  >
                    <LoaderCircle className="mt-0.5 size-4 shrink-0 animate-spin text-primary" />
                    <div>
                      <p className="font-medium">
                        {importProgress?.phase === "processing"
                          ? "文件已上传，正在提炼语料"
                          : "正在将文件上传到服务器"}
                      </p>
                      <p className="mt-0.5 text-xs leading-5 text-muted-foreground">
                        {importProgress?.phase === "processing"
                          ? "AI 解析大文件可能需要数分钟，请保持页面打开。"
                          : "上传完成后会自动开始 AI 解析。"}
                      </p>
                    </div>
                  </Alert>
                )}
                {importMessage && <Alert className="border-success/25 bg-success/5 text-sm text-success">{importMessage}</Alert>}
              </div>
            ) : (
            <form className="grid gap-4" onSubmit={handleSubmit}>
              <div className="grid gap-2">
                <Label htmlFor="corpus-category">语料分类</Label>
                <select
                  id="corpus-category"
                  value={category}
                  onChange={(event) => setCategory(event.target.value)}
                  className="h-10 rounded-lg border border-input bg-card px-3 text-sm shadow-[0_1px_2px_hsl(var(--shadow-color)/0.025)] outline-none transition-[border-color,box-shadow] focus-visible:border-primary/50 focus-visible:ring-3 focus-visible:ring-ring/15"
                >
                  {categoryGroups.map((group) => (
                    <optgroup key={group.label} label={group.label}>
                      {group.options.map(([value, label]) => (
                        <option key={value} value={value}>
                          {label}
                        </option>
                      ))}
                    </optgroup>
                  ))}
                </select>
              </div>
              <div className="grid gap-2">
                <Label htmlFor="corpus-title">标题</Label>
                <Input
                  id="corpus-title"
                  value={title}
                  onChange={(event) => setTitle(event.target.value)}
                  placeholder="例如：星越L智驾版核心卖点"
                  maxLength={100}
                  required
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="corpus-content">具体内容</Label>
                <Textarea
                  id="corpus-content"
                  value={content}
                  onChange={(event) => setContent(event.target.value)}
                  placeholder="填写准确口径、目标区间、预警阈值、诊断规则或推荐话术。"
                  maxLength={12000}
                  className="min-h-56"
                  required
                />
                <p className="text-right text-xs tabular-nums text-muted-foreground">
                  {content.length}/12000
                </p>
              </div>
              <div className="flex gap-2">
                <Button
                  type="submit"
                  disabled={saving || !title.trim() || !content.trim()}
                >
                  {saving ? (
                    <LoaderCircle data-icon="inline-start" className="animate-spin" />
                  ) : editingId === null ? (
                    <Plus data-icon="inline-start" />
                  ) : (
                    <Save data-icon="inline-start" />
                  )}
                  {editingId === null ? "添加到语料库" : "保存修改"}
                </Button>
                {editingId !== null && (
                  <Button type="button" variant="outline" onClick={resetForm}>
                    <X data-icon="inline-start" />
                    取消
                  </Button>
                )}
              </div>
            </form>
            )}
          </CardContent>
        </Card>

        <Card className="bg-card/90">
          <CardHeader className="border-b border-border/60">
            <CardTitle className="flex items-center gap-2">
              <BookOpenText className="size-4 text-primary" />
              已保存语料
            </CardTitle>
            <CardDescription>停用后仍会保留，但不会进入AI实时分析。</CardDescription>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="grid gap-3">
                {[0, 1, 2].map((item) => (
                  <div key={item} className="h-32 animate-pulse rounded-xl bg-muted" />
                ))}
              </div>
            ) : entries.length === 0 ? (
              <div className="grid min-h-64 place-items-center text-center">
                <div>
                  <BookOpenText className="mx-auto size-9 text-muted-foreground" />
                  <p className="mt-3 text-sm font-medium">暂无个性化语料</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    从左侧录入第一条车型卖点、指标目标或诊断规则。
                  </p>
                </div>
              </div>
            ) : (
              <div className="grid gap-3">
                {entries.map((entry) => (
                  <article key={entry.id} className="rounded-xl border border-border/70 bg-background/45 p-4 transition-[border-color,background-color,box-shadow] hover:border-primary/20 hover:bg-card hover:shadow-[0_8px_24px_hsl(var(--shadow-color)/0.045)]">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <h2 className="text-sm font-semibold">{entry.title}</h2>
                          <Badge variant="outline">{categoryLabel(entry.category)}</Badge>
                          <Badge variant={entry.enabled ? "success" : "secondary"}>
                            {entry.enabled ? "已启用" : "已停用"}
                          </Badge>
                          {entry.source_type && (
                            <Badge variant="secondary">{entry.source_type.toUpperCase()} 导入</Badge>
                          )}
                        </div>
                        <p className="mt-1 text-xs text-muted-foreground">
                          更新于 {formatDateTime(entry.updated_at)}
                        </p>
                      </div>
                      <div className="flex gap-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => void toggleEntry(entry)}
                        >
                          <CheckCircle2 data-icon="inline-start" />
                          {entry.enabled ? "停用" : "启用"}
                        </Button>
                        <Button variant="ghost" size="sm" onClick={() => beginEdit(entry)}>
                          <Pencil data-icon="inline-start" />
                          编辑
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-destructive hover:text-destructive"
                          onClick={() => void removeEntry(entry)}
                        >
                          <Trash2 data-icon="inline-start" />
                          删除
                        </Button>
                      </div>
                    </div>
                    <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-muted-foreground">
                      {entry.content}
                    </p>
                  </article>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </section>
  )
}

function categoryLabel(category: string) {
  return categories.find(([value]) => value === category)?.[1] ?? category
}

function formatFileSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}
