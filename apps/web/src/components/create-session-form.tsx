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
  const [platform, setPlatform] = useState<Platform>("douyin")

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    await onCreate({
      title: title.trim(),
      room_name: roomName.trim(),
      operator_name: operatorName.trim() || "内部优化师",
      platform,
    })
    setTitle("")
    setRoomName("")
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>新建监控场次</CardTitle>
        <CardDescription>
          创建后，在Windows采集助手中输入场次ID并开始采集。
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
                  className="flex cursor-pointer items-center gap-2 rounded-md border bg-background px-3 py-2 text-sm has-[:checked]:border-primary has-[:checked]:bg-primary/5"
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

