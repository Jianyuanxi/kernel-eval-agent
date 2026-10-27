export const FEATURE_NAMES = {
  F_UART: '串口打印',
  F_EXC: '异常处理',
  F_TIMER: '时钟中断',
  F_TASK: '任务创建与切换',
  F_SCHED: '任务调度',
  F_SEM: '信号量',
  F_SHELL: 'shell 命令',
  F_INNOV: '创新功能',
}

export const KNOWLEDGE_NAMES = {
  K_MEM: '内存管理（内存的分配与回收）',
  K_ADDR: '地址空间与内存保护',
  K_SYNC: '进程同步与互斥、死锁的四个必要条件',
  K_CRIT: '临界区、竞态条件',
  K_IRQ: '中断机制',
  K_CTX: '进程控制块与上下文切换',
  K_SYSCALL: '系统调用、用户态与内核态隔离',
  K_DEV: '文件系统与设备管理',
  K_GENERAL: '通用编程规范与健壮性',
}

export const FEATURE_STATUS = { done: '完成', partial: '部分完成', none: '未完成' }
export const STYLE_GRADE = { good: '好', medium: '中', poor: '差' }
export const SEVERITY_RANK = { 严重: 0, 一般: 1, 轻微: 2 }

export const STATUS_LABEL = {
  passed: '通过',
  failed: '失败',
  timeout: '超时',
  skipped: '跳过',
  unsupported: '不支持',
  error: '出错',
}
