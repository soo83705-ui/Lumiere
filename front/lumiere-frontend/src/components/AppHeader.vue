<template>
  <header class="app-header">
    <div class="logo">
      <RouterLink to="/">Lumière</RouterLink>
    </div>

    <nav class="nav-menu">
      <RouterLink to="/upload" class="nav-item">진단하기</RouterLink>
      <RouterLink to="/product-analysis" class="nav-item">제품 분석</RouterLink>
      <RouterLink to="/products" class="nav-item">추천 제품</RouterLink>
      <RouterLink to="/community" class="nav-item">커뮤니티</RouterLink>
      <RouterLink to="/mypage" class="nav-item">마이페이지</RouterLink>
    </nav>

    <div class="header-right">
      <input placeholder="제품명, 브랜드, 색상 검색" />
      
      <button v-if="!isLoggedIn" class="login-btn" @click="$router.push('/login')">
        로그인
      </button>
      
      <div v-else class="user-area">
        <span>🔔</span>
        <span>♡</span>
        <div class="profile"></div>
        <span>안녕하세요, {{ userName }}님⌄</span>
        <span class="logout-text" @click="logout">로그아웃</span>
      </div>

    </div>
  </header>
</template>

<script setup>
import { ref } from 'vue'

// 💡 테스트용 임시 로그인 상태 변수입니다.
// 이 값을 true 로 바꾸고 저장하시면 화면이 로그인된 상태로 즉시 변합니다!
const isLoggedIn = ref(false) 
const userName = ref('박성은') // 유저 이름 데이터

// 임시 로그아웃 함수
const logout = () => {
  isLoggedIn.value = false
  alert('로그아웃 되었습니다.')
}
</script>

<style scoped>
.app-header {
  height: 72px;
  padding: 0 42px;
  border-bottom: 1px solid #eaded8;
  background: rgba(255, 250, 247, 0.95);

  display: flex;
  align-items: center;
  justify-content: space-between;
}

.logo {
  font-family: Georgia, serif;
  font-size: 30px;
  font-weight: 700;
  color: #bf4f63;
}

.nav {
  display: flex;
  gap: 56px;
  font-size: 15px;
  font-weight: 600;
}

.nav a {
  cursor: pointer;
}

.user-area {
  display: flex;
  align-items: center;
  gap: 18px;
  font-size: 14px;
}

.profile {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: linear-gradient(135deg, #f5d6c8, #fff1ea);
}
.header-right {
  display: flex;
  gap: 16px;
  align-items: center;
}

.header-right input {
  width: 280px;
  padding: 13px 18px;
  border: 1px solid #eaded8;
  border-radius: 10px;
  background: white;
}

.login-btn {
  background: #c65367;
  color: white;
  border: none;
  border-radius: 8px;
  padding: 13px 24px;
  cursor: pointer;
}
.app-header {
  height: 72px;
  padding: 0 42px;
  border-bottom: 1px solid #eaded8;
  background: rgba(255, 250, 247, 0.95);
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.logo {
  font-family: Georgia, serif;
  font-size: 30px;
  font-weight: 700;
  color: #bf4f63;
}
.logo a {
  text-decoration: none;
  color: inherit;
}

.nav-menu {
  display: flex;
  gap: 56px;
  font-size: 15px;
  font-weight: 600;
}

.nav-item {
  color: #333;
  text-decoration: none;
}

.header-right {
  display: flex;
  gap: 16px;
  align-items: center;
}

.header-right input {
  width: 280px;
  padding: 13px 18px;
  border: 1px solid #eaded8;
  border-radius: 10px;
  background: white;
}

.login-btn {
  background: #c65367;
  color: white;
  border: none;
  border-radius: 8px;
  padding: 13px 24px;
  cursor: pointer;
}

.user-area {
  display: flex;
  align-items: center;
  gap: 18px;
  font-size: 14px;
}

.profile {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: linear-gradient(135deg, #f5d6c8, #fff1ea);
}

.logout-text {
  font-size: 12px;
  color: #888;
  cursor: pointer;
  text-decoration: underline;
  margin-left: 8px;
}
</style>