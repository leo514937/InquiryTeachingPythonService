<template>
  <main class="auth-shell">
    <section class="auth-card glass">
      <p class="eyebrow">AI 教师探究式教学指导平台</p>
      <h1>{{ accountType === "admin" ? (mode === "login" ? "管理员登录" : "注册管理员") : (mode === "login" ? "登录工作台" : "创建账号") }}</h1>
      <p class="auth-subtitle">
        {{ accountType === "admin" ? "管理员可维护全局课标知识库。" : (mode === "login" ? "登录后查看和管理自己的教案会话。" : "注册后即可开始创建属于自己的教案会话。") }}
      </p>

      <div class="auth-account-tabs" role="tablist" aria-label="登录身份">
        <button
          class="auth-account-tab"
          :class="{ active: accountType === 'user' }"
          type="button"
          role="tab"
          :aria-selected="accountType === 'user'"
          @click="switchAccountType('user')"
        >
          普通用户
        </button>
        <button
          class="auth-account-tab"
          :class="{ active: accountType === 'admin' }"
          type="button"
          role="tab"
          :aria-selected="accountType === 'admin'"
          @click="switchAccountType('admin')"
        >
          管理员
        </button>
      </div>

      <form class="auth-form" @submit.prevent="submit">
        <label class="auth-field">
          <span>用户名</span>
          <input
            v-model.trim="username"
            class="input"
            name="username"
            autocomplete="username"
            minlength="3"
            maxlength="32"
            pattern="[A-Za-z0-9_]+"
            required
            placeholder="3–32 位字母、数字或下划线"
          />
        </label>
        <label class="auth-field">
          <span>密码</span>
          <input
            v-model="password"
            class="input"
            name="password"
            type="password"
            :autocomplete="mode === 'login' ? 'current-password' : 'new-password'"
            minlength="8"
            maxlength="128"
            required
            placeholder="至少 8 位"
          />
        </label>

        <p v-if="errorMessage" class="auth-error">{{ errorMessage }}</p>
        <button class="primary-button auth-submit" type="submit" :disabled="submitting">
          {{ submitting ? "处理中…" : mode === "login" ? (accountType === "admin" ? "管理员登录" : "登录") : (accountType === "admin" ? "注册管理员并登录" : "注册并登录") }}
        </button>
      </form>

      <button class="ghost-button auth-switch" type="button" @click="switchMode">
        {{ mode === "login" ? (accountType === "admin" ? "还没有管理员账号？注册" : "还没有账号？注册") : "已有账号？返回登录" }}
      </button>
    </section>
  </main>
</template>

<script setup lang="ts">
import { ref } from "vue";

import { loginAdmin, loginUser, registerAdmin, registerUser } from "@/api";
import type { AuthUser } from "@/types";

const emit = defineEmits<{
  authenticated: [user: AuthUser];
}>();

const mode = ref<"login" | "register">("login");
const accountType = ref<"user" | "admin">("user");
const username = ref("");
const password = ref("");
const errorMessage = ref("");
const submitting = ref(false);

function extractError(error: unknown): string {
  const raw = error instanceof Error ? error.message : "操作失败，请稍后重试";
  try {
    const parsed = JSON.parse(raw);
    return parsed.detail || "操作失败，请稍后重试";
  } catch {
    return raw;
  }
}

function switchMode() {
  mode.value = mode.value === "login" ? "register" : "login";
  errorMessage.value = "";
  password.value = "";
}

function switchAccountType(nextType: "user" | "admin") {
  accountType.value = nextType;
  mode.value = "login";
  errorMessage.value = "";
  password.value = "";
}

async function submit() {
  errorMessage.value = "";
  submitting.value = true;
  try {
    const user = accountType.value === "admin"
      ? mode.value === "login"
        ? await loginAdmin(username.value, password.value)
        : await registerAdmin(username.value, password.value)
      : mode.value === "login"
        ? await loginUser(username.value, password.value)
        : await registerUser(username.value, password.value);
    emit("authenticated", user);
  } catch (error) {
    errorMessage.value = extractError(error);
  } finally {
    submitting.value = false;
  }
}
</script>
