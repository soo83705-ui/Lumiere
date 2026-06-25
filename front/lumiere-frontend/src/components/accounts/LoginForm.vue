<template>
  <form @submit.prevent="handleLogin" class="login-form">
    <div class="input-group">
      <label>아이디</label>
      <input type="text" v-model.trim="username" placeholder="아이디를 입력해주세요" required />
    </div>

    <div class="input-group">
      <label>비밀번호</label>
      <input type="password" v-model.trim="password" placeholder="비밀번호를 입력해주세요" required />
    </div>

    <button type="submit" class="login-btn">로그인</button>

    <div class="login-options">
      <span class="find-password-text" @click="goToFindPassword">비밀번호를 잊으셨나요?</span>
    </div>
  </form>
</template>

<script setup>
import { ref } from 'vue'
// 1. useRouter를 추가로 import 해줘
import { useRoute, useRouter } from 'vue-router'
import axios from 'axios'
import { API_BASE_URL } from '@/config/api'

const emit = defineEmits(['goToFindPassword'])

const username = ref('')
const password = ref('')
const route = useRoute()
// 2. router 객체 초기화
const router = useRouter()

const handleLogin = async () => { 
  const loginData = {
    username: username.value,
    password: password.value,
  }

  try {
    const response = await axios.post(
      `${API_BASE_URL}/accounts/jwt-login/`,
      loginData,
      { headers: { 'ngrok-skip-browser-warning': 'true' } },
    )

    const accessToken = response.data.access || response.data.access_token || response.data.token?.access
    const refreshToken = response.data.refresh || response.data.refresh_token || response.data.token?.refresh

    if (!accessToken) {
      alert('로그인 응답 형식이 올바르지 않습니다.')
      return
    }

    localStorage.setItem('access_token', accessToken)
    if (refreshToken) {
      localStorage.setItem('refresh_token', refreshToken)
    }

    alert('로그인에 성공했습니다!')

    // 3. 리다이렉트 경로 보정 및 라우터 전환 로직
    let redirectPath = typeof route.query.redirect === 'string' && route.query.redirect.startsWith('/')
      ? route.query.redirect
      : '/'

    // 외부 유입 시 /login 자체가 리다이렉트로 잡혀 튕기는 루프 방지
    if (redirectPath.includes('/login')) {
      redirectPath = '/'
    }

    // window.location.href 대신 Vue 라우터 사용
    router.push(redirectPath).then(() => {
      // 컴포넌트가 마운트된 상태에서도 헤더가 갱신되도록 이벤트 발송
      window.dispatchEvent(new Event('auth-updated'))
    })

  } catch (error) {
    console.error('로그인 실패:', error.response?.data || error)
    alert('아이디 또는 비밀번호가 올바르지 않습니다.')
  }
}

const goToFindPassword = () => {
  emit('goToFindPassword')
}
</script>

<style scoped>
.login-form {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.input-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.input-group label {
  font-weight: bold;
  font-size: 0.9rem;
  color: #333;
}

.input-group input {
  padding: 12px 16px;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  outline: none;
}

.input-group input:focus {
  border-color: #8b3a4a;
}

.login-btn {
  padding: 15px;
  background-color: #8b3a4a;
  color: white;
  border: none;
  border-radius: 8px;
  font-weight: bold;
  cursor: pointer;
  margin-top: 10px;
}

/* ★ 비밀번호 찾기 텍스트 스타일 */
.login-options {
  text-align: center;
  margin-top: -5px;
}

.find-password-text {
  font-size: 0.85rem;
  color: #888;
  text-decoration: underline;
  cursor: pointer;
  transition: color 0.2s ease-in-out;
}

.find-password-text:hover {
  color: #8b3a4a;
}
</style>
