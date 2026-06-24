---
create_date: 2026-06-24T16:09:00
update: 2026-06-24
status: draft
---

# P1-A电脑端技术规格

## 一、当前定位

P1-A不是普通Todolist，也不是完整AI学习助手。

P1-A的目标是先完成：

> 家长在电脑端制定学习计划，学生通过ESP32-S3-BOX-3语音交互执行计划，电脑端负责调度、计时、状态管理、播报生成和统计记录。

第一版真实设备未接入前，使用虚拟设备模拟ESP32-S3-BOX-3。

## 二、已确认产品边界

- 第一版使用者分工：
  - 家长使用电脑端Web管理页面。
  - 学生不使用电脑端页面。
  - 学生主要通过ESP32-S3-BOX-3语音交互执行学习任务。
- 第一版只支持一个学生。
  - 数据库保留`student_id`字段。
  - 页面暂不做多学生切换。
- 支持手机闹钟式日历计划。
  - 家长在日历上设置计划。
  - 计划可以按日期范围和星期重复。
  - 没有设置计划的日期不生成任务，也不提醒。
  - 单日修改只影响当天。
- 休息作为独立任务存在。
- “开始学习”默认启动当前时间附近、未完成、优先级最高的任务。
- 计划结束时间到达不等于任务完成。
  - 系统进入待确认结束状态。
  - 学生通过语音确认完成、继续、延长或跳过。
- 完成任务的主流程来自语音通讯。
  - Web端的完成、修正、跳过属于家长后台纠错能力。
- 真实BOX-3接入前，先支持电脑播报和虚拟设备模拟。
- 第一版统计包括：
  - 今日计划数
  - 完成数
  - 跳过数
  - 计划学习分钟
  - 有效学习分钟
  - 延迟开始
  - 科目占比
- 法定节假日支持联网自动同步，并允许本地缓存和家长修正。
- 寒暑假由家长设置日期范围，作为日历标签存在。
- 法定节假日和寒暑假不是独立计划来源，只影响计划是否执行。
- 重复计划默认遇法定节假日照常执行，家长可设置自动跳过。
- 重复计划可设置是否在寒暑假执行。

## 三、技术原则

### 1. 后端是状态权威

学习状态、当前任务、有效时长、提醒记录和统计结果都以后端为准。

ESP32-S3-BOX-3只负责：

- 接收播报
- 显示状态
- 采集或识别学生命令
- 上报命令事件
- 上报播放结果
- 上报在线状态

### 2. 后端不依赖真实设备，但按真实设备设计

第一阶段不开发真实固件，但后端必须从第一天支持设备协议。

不能只“预留接口”。必须实现：

- 统一命令入口
- WebSocket设备通道
- 虚拟设备模拟器
- 后端主动推送播报和状态
- 设备事件驱动状态机

### 3. Web端是家长控制台

Web端用于：

- 制定计划
- 维护日历计划
- 查看设备在线状态
- 查看当前任务状态
- 查看今日统计
- 手动纠错
- 修改播报模板

Web端不是学生学习执行主入口。

## 四、建议技术栈

第一版建议使用：

- 后端：Python FastAPI
- 数据库：SQLite
- ORM：SQLModel或SQLAlchemy
- 任务调度：APScheduler
- 实时通信：WebSocket
- Web前端：FastAPI模板页面或轻量前端
- 设备模拟器：Python CLI程序
- 数据格式：JSON

暂不使用：

- MQTT
- 微服务
- 云端部署
- 复杂权限系统
- 多设备管理平台
- ESP-IDF真实固件开发

## 五、核心数据模型

### 1. Student

第一版只有一个学生，但保留学生模型。

建议字段：

```text
id
name
created_at
updated_at
```

### 2. SchedulePlan

手机闹钟式日历计划。

建议字段：

```text
id
student_id
name
start_date
end_date
repeat_rule
skip_public_holidays
run_in_winter_vacation
run_in_summer_vacation
is_active
created_at
updated_at
```

`repeat_rule`第一版可以简化为：

```json
{
  "weekdays": [1, 2, 3, 4, 5]
}
```

没有设置计划的日期不生成任务。

### 3. ScheduleTaskItem

日历计划中的任务项。

建议字段：

```text
id
schedule_plan_id
sort_order
task_kind
subject
title
content
planned_start_time
planned_end_time
planned_minutes
remind_enabled
pre_remind_minutes
created_at
updated_at
```

`task_kind`建议枚举：

```text
study
practice
review
homework
recitation
reading
break
```

### 4. ScheduleException

单日例外。

建议字段：

```text
id
schedule_plan_id
date
exception_type
override_payload
reason
created_at
updated_at
```

`exception_type`建议枚举：

```text
skip
override
```

第一版规则：

- `skip`：当天不生成该计划。
- `override`：当天使用修改后的任务项，只影响当天。

### 5. HolidayCalendar

节假日和寒暑假日期标签。

建议字段：

```text
id
date
label
day_type
source
is_rest_day
created_at
updated_at
```

`day_type`建议枚举：

```text
public_holiday
makeup_workday
winter_vacation
summer_vacation
custom_label
```

说明：

- 法定节假日通过联网自动同步，并保存在本地。
- 寒暑假由家长设置日期范围。
- 日期标签不是计划来源，只影响已有日历计划是否执行。

### 6. DailyTask

某一天真实执行的计划任务。

建议字段：

```text
id
student_id
source_schedule_plan_id
source_schedule_task_item_id
date
sort_order
task_kind
subject
title
content
original_start_at
original_end_at
current_start_at
current_end_at
planned_minutes
status
modify_count
created_at
updated_at
```

`original_*`用于保留最初计划，`current_*`用于当前调整后的计划。

### 7. StudySession

一次任务执行会话。

建议字段：

```text
id
daily_task_id
student_id
status
started_at
ended_at
completed_at
paused_total_seconds
effective_seconds
finish_source
created_at
updated_at
```

`finish_source`建议枚举：

```text
voice
web_correction
system
```

### 8. TimeSegment

有效计时段。

任务暂停后继续，会产生多个计时段。

建议字段：

```text
id
study_session_id
started_at
ended_at
duration_seconds
created_at
```

### 9. ReminderEvent

提醒记录。

建议字段：

```text
id
daily_task_id
event_type
scheduled_at
sent_at
ack_at
device_id
status
message_text
created_at
updated_at
```

`event_type`建议枚举：

```text
pre_start
start_due
end_due
break_start
break_end
delayed_start
finish_confirm
```

### 10. Device

设备记录。

建议字段：

```text
id
device_id
name
device_type
firmware_version
status
last_seen_at
created_at
updated_at
```

第一版设备类型固定为：

```text
esp32_s3_box_3
virtual_box_3
```

## 六、任务状态机

### 1. DailyTask状态

建议枚举：

```text
pending
reminding
studying
paused
waiting_finish_confirm
completed
skipped
overdue
```

含义：

- `pending`：待开始。
- `reminding`：已经到提醒时间，正在提醒。
- `studying`：学习或休息正在计时。
- `paused`：学习中暂停。
- `waiting_finish_confirm`：计划结束时间到了，等待学生确认。
- `completed`：学生确认完成。
- `skipped`：跳过。
- `overdue`：长时间未开始或未确认。

### 2. 核心流转

```text
pending
  -> reminding
  -> studying
  -> paused
  -> studying
  -> waiting_finish_confirm
  -> completed
```

跳过流转：

```text
pending/reminding/studying/paused/waiting_finish_confirm
  -> skipped
```

计划到点但无回应：

```text
pending
  -> reminding
  -> overdue
```

计划结束但无确认：

```text
studying
  -> waiting_finish_confirm
  -> overdue
```

## 七、统一命令入口

所有执行命令都进入同一个后端命令处理器。

命令来源可以是：

- `device_voice`
- `virtual_device`
- `web_admin`
- `scheduler`

第一版核心命令：

```text
START_STUDY
PAUSE_STUDY
RESUME_STUDY
COMPLETE_STUDY
SKIP_TASK
QUERY_CURRENT_TASK
QUERY_TODAY_PLAN
EXTEND_CURRENT_TASK
EXTEND_BREAK
STOP_SPEAKING
```

命令处理器职责：

- 查找当前任务
- 校验状态是否允许流转
- 更新任务和会话
- 生成播报文本
- 推送设备显示状态
- 记录事件日志

## 八、设备通信协议

### 1. 连接方式

第一版使用WebSocket。

建议路径：

```text
/ws/device/{device_id}
```

### 2. 设备注册

设备连接后上报：

```json
{
  "type": "device_hello",
  "device_id": "box3-001",
  "device_type": "esp32_s3_box_3",
  "firmware_version": "0.1.0",
  "timestamp": "2026-06-24T19:00:00+08:00"
}
```

虚拟设备：

```json
{
  "type": "device_hello",
  "device_id": "virtual-box3-001",
  "device_type": "virtual_box_3",
  "firmware_version": "virtual-0.1.0",
  "timestamp": "2026-06-24T19:00:00+08:00"
}
```

### 3. 设备上报语音命令

```json
{
  "type": "voice_command",
  "device_id": "box3-001",
  "command": "START_STUDY",
  "text": "开始学习",
  "timestamp": "2026-06-24T19:00:05+08:00"
}
```

### 4. 设备上报播放完成

```json
{
  "type": "playback_finished",
  "device_id": "box3-001",
  "message_id": "msg-1001",
  "timestamp": "2026-06-24T19:00:12+08:00"
}
```

### 5. 后端下发播报

```json
{
  "type": "speak",
  "message_id": "msg-1001",
  "priority": "high",
  "text": "现在应该开始数学作业，计划学习四十分钟。请说开始学习。",
  "timestamp": "2026-06-24T19:00:00+08:00"
}
```

### 6. 后端下发屏幕状态

```json
{
  "type": "display_state",
  "state": "reminding",
  "task": {
    "title": "数学作业",
    "subject": "数学",
    "planned_minutes": 40
  },
  "timestamp": "2026-06-24T19:00:00+08:00"
}
```

### 7. 后端同步当前状态

```json
{
  "type": "sync_state",
  "current_task": {
    "id": "task-001",
    "title": "数学作业",
    "status": "studying",
    "effective_seconds": 600,
    "planned_minutes": 40
  },
  "device_status": "online",
  "timestamp": "2026-06-24T19:10:00+08:00"
}
```

## 九、调度器

调度器负责产生系统事件。

第一版需要：

- 提前提醒
- 到点开始提醒
- 计划结束提醒
- 休息开始提醒
- 休息结束提醒
- 延迟未开始提醒
- 待确认结束重复提醒

调度器不直接修改复杂业务状态，应调用统一命令或事件处理服务。

## 十、虚拟设备模拟器

虚拟设备必须和真实设备使用同一套协议。

建议功能：

- 连接后端WebSocket
- 发送`device_hello`
- 接收`speak`并打印播报内容
- 接收`display_state`并打印屏幕状态
- 命令行输入转换为语音命令

命令行输入示例：

```text
start      -> START_STUDY
pause      -> PAUSE_STUDY
resume     -> RESUME_STUDY
complete   -> COMPLETE_STUDY
skip       -> SKIP_TASK
current    -> QUERY_CURRENT_TASK
today      -> QUERY_TODAY_PLAN
```

## 十一、Web管理端页面

第一版页面建议：

### 1. 今日计划

- 今日任务列表
- 当前状态
- 计划时间
- 实际开始时间
- 有效学习时长
- 延迟开始

### 2. 当前任务

- 当前任务名称
- 状态
- 计时
- 设备在线状态
- 最近播报

### 3. 日历计划

- 创建日历计划
- 设置重复星期
- 添加学习任务
- 添加休息任务

### 4. 今日统计

- 今日计划数
- 完成数
- 跳过数
- 计划学习分钟
- 有效学习分钟
- 延迟开始
- 科目占比

### 5. 家长纠错

- 手动修改任务状态
- 修正实际开始时间
- 修正实际结束时间
- 标记误触发命令

## 十二、第一版验收标准

不接真实BOX-3时，必须能完成以下闭环：

```text
家长创建日历计划
-> 生成今日计划
-> 调度器到点提醒
-> 虚拟设备收到播报
-> 虚拟设备输入start
-> 后端开始计时
-> 到计划结束时间
-> 后端播报请求确认
-> 虚拟设备输入complete
-> 后端记录完成
-> Web端显示今日统计
```

验收时必须验证：

- 任务和计时段分开记录。
- 暂停时间不计入有效学习时间。
- 休息任务和学习任务都能执行。
- 到结束时间不会自动完成。
- 完成命令可以来自虚拟设备。
- Web端可以纠错，但不是主执行入口。
- 设备断开后Web端能看到离线状态。

## 十三、暂不开发内容

- 真实ESP32-S3-BOX-3固件
- WakeNet唤醒词
- MultiNet本地命令识别
- 真实麦克风采集
- 真实扬声器播放
- BOX-3屏幕UI实现
- 自然语言计划修改
- ASR语音转文字
- 云端同步
- 多学生管理
- 多设备管理
- AI学习诊断

这些内容进入后续阶段。
