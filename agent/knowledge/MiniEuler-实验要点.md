# MiniEuler 实验要点（八个功能点）

MiniEuler 是 UniProton 的教学精简版：CMake 交叉编译到 ARM64，QEMU `virt` 机运行，串口当控制台。评审时按功能点对照“关键文件 / 函数 / 运行现象”，下面按 `F_*` 归纳一般实现位置（具体路径以学生工程为准）。

## F_UART 串口输出

板级串口（如 PL011）初始化、字符输出与 `PRT_Printf` / `print.c` 一类封装。启动日志、shell 提示符、回显都依赖它。运行证据看启动输出 R1 里是否有可读打印；代码常在 `src/bsp/pl011.c`、`src/bsp/print.c`。

## F_EXC 异常处理

异常向量表与入口（`prt_vector.S` / `prt_exc.c` 等），同步/异步异常时保存现场、打印或停机。要点：向量基址配置正确，入口不会破坏其它寄存器约定。

## F_TIMER 时钟中断

通用定时器或架构定时器初始化（`timer.c`）、tick 递增（`prt_tick.c`）、在中断里驱动调度时间片。运行中周期性行为、`tick` 类 shell 命令可作旁证。

## F_TASK 任务创建与切换

任务控制块、栈、`PRT_TaskCreate` / 任务初始化（`prt_task.c`、`prt_task_init.c`）。切换时保存/恢复通用寄存器与栈指针；不完整保存属于 `CONTEXT_SAVE` 类缺陷。

## F_SCHED 任务调度

就绪队列与选下一个任务（`prt_sched_single.c` 等）。时钟中断或主动让出时进入调度；注意关中断临界区与 `OsTskScheduleFastPs` 的用法。

## F_SEM 信号量

`prt_sem.c` / `prt_sem_init.c`：`PRT_SemCreate`、`Pend`、`Post`。实现里常见 `OsIntLock` 保护等待队列；每个返回分支恢复中断；阻塞路径正确挂起当前任务。

## F_SHELL shell 命令

shell 任务一般从 UART 环形缓冲取字符、写入定长命令缓冲、解析并调用显示函数（如 `top`/`tick`/`mem`）。组命令时要保证下标不超过命令数组容量；运行证据看 R2 及后续命令输出。相关代码常在 `shmsg.c` 与 shell 初始化路径。

## F_INNOV 创新功能

学生在 README、说明文档或注释中声称的扩展（新命令、统计、调度策略等）。要在源码里找到对应实现，不能只写在文档里；`innovation.found_in_code` 必须与代码一致。

## 评审时建议的阅读顺序

1. `list_files` 看目录；`diff_reference` 看学生改了哪些文件。  
2. `compile_project` / `run_kernel` / `clang_scan` 拿 B/R/C 证据。  
3. 优先 `read_source`：shell、sem、sched、task、tick、bsp 打印与异常。  
4. 功能点状态：有运行输出证明优先引用 R；纯片段工程只能依据代码判 partial/done/none。
