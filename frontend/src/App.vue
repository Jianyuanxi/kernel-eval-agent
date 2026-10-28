<template>
  <div class="app-shell">
    <header class="topbar">
      <router-link to="/" class="brand">内核代码评测</router-link>
      <span class="topbar-note">操作系统课程 · 上传作业后自动编译、运行并生成报告</span>
    </header>
    <main class="page">
      <router-view />
    </main>
  </div>
</template>
