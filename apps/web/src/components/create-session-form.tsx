import { useState, type FormEvent } from "react"
import { LoaderCircle, Plus } from "lucide-react"

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
import type { Platform, SessionCreateInput } from "@/types"

interface CreateSessionFormProps {
  operatorName: string
  pending: boolean
  onCreate: (input: SessionCreateInput) => Promise<void>
}

export function CreateSessionForm({
  operatorName,
  pending,
  onCreate,
}: CreateSessionFormProps) {
  const [title, setTitle] = useState("")
  const [roomName, setRoomName] = useState("")
  const [liveUrl, setLiveUrl] = useState("")
  const [platform, setPlatform] = useState<Platform>("douyin")

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    await onCreate({
      title: title.trim(),
      room_name: roomName.trim(),
      live_url: liveUrl.trim(),
      operator_name: operatorName.trim() || "内部优化师",
      platform,
    })
    setTitle("")
    setRoomName("")
    setLiveUrl("")
  }

  return (
    <Card className="bg-card/80">
      <CardHeader className="border-b border-border/60">
        <CardTitle>新建监控场次</CardTitle>
        <CardDescription>
          创建后，在直播标签页的浏览器扩展中输入场次ID并开始采集。
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form className="grid gap-4" onSubmit={handleSubmit}>
          <div className="grid gap-2">
            <Label htmlFor="session-title">场次名称</Label>
            <Input
              id="session-title"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="例如：8月4日上午盯播"
              required
            />
          </div>

          <fieldset className="grid gap-2">
            <legend className="text-sm font-medium">直播平台</legend>
            <div className="grid grid-cols-2 gap-2">
              {[
                ["douyin", "抖音"],
                ["dongchedi", "懂车云店"],
              ].map(([value, label]) => (
                <label
                  key={value}
                  className="flex cursor-pointer items-center gap-2 rounded-lg border border-input bg-card px-3 py-2.5 text-sm transition-colors hover:bg-muted/60 has-[:checked]:border-primary/60 has-[:checked]:bg-primary/7 has-[:checked]:ring-2 has-[:checked]:ring-primary/10"
                >
                  <input
                    type="radio"
                    name="platform"
                    value={value}
                    checked={platform === value}
                    onChange={() => setPlatform(value as Platform)}
                    className="accent-primary"
                  />
                  {label}
                </label>
              ))}
            </div>
          </fieldset>

          <div className="grid gap-2">
            <Label htmlFor="live-url">直播间链接</Label>
            <Input
              id="live-url"
              type="url"
              value={liveUrl}
              onChange={(event) => setLiveUrl(event.target.value)}
              placeholder={
                platform === "douyin"
                  ? "https://live.douyin.com/..."
                  : "https://www.autoengine.com/jdc/industry/live/screen?room_id=..."
              }
            />
            <p className="text-xs leading-5 text-muted-foreground">
              选填。浏览器扩展会采集标签页声音，并同步懂车云店大屏指标。
            </p>
          </div>

          <div className="grid gap-2">
            <Label htmlFor="room-name">直播间备注</Label>
            <Input
              id="room-name"
              value={roomName}
              onChange={(event) => setRoomName(event.target.value)}
              placeholder="选填"
            />
          </div>

          <Button type="submit" disabled={pending || !title.trim()}>
            {pending ? (
              <LoaderCircle className="animate-spin" />
            ) : (
              <Plus data-icon="inline-start" />
            )}
            创建场次
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}

