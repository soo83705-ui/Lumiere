# Lumiere

# 📂 Lumiere 프로젝트 구조 (Project Structure)

이 섹션은 Lumiere 프로젝트의 디렉토리 구성과 각 앱의 역할을 설명합니다.

```text
project01_26/                  # 전체 프로젝트 루트 (Root)
├── manage.py                  # Django 프로젝트 관리 실행 파일
├── .gitignore                 # Git 관리 제외 설정
├── requirements.txt           # 프로젝트 의존성 라이브러리 목록
├── README.md                  # 프로젝트 설명 문서
│
├── Lumiere/                   # [Project] 메인 설정 디렉토리
│   ├── settings.py            # 데이터베이스, 앱 등록 등 전역 설정
│   ├── urls.py                # 최상위 URL 라우팅
│   ├── asgi.py                # 비동기 서버 설정
│   └── wsgi.py                # 웹 서버 인터페이스 설정
│
├── accounts/                  # [App] 사용자 관리 (Auth)
│   ├── models.py              # 커스텀 User 모델 (프로필, 닉네임 등)
│   ├── views.py               # 로그인, 회원가입, 로그아웃 로직
│   └── migrations/            # DB 변경 이력 관리
│
├── personal_color/            # [App] 퍼스널 컬러 진단 및 관리
│   ├── models.py              # 진단 결과(봄/여름/가을/겨울), 진단 히스토리
│   ├── views.py               # AI 모델 연동 및 진단 처리 로직
│   ├── fixtures/              # 컬러 타입 기본 데이터 (Initial Data)
│   ├── templates/
│   │   └── personal_color/    # 진단 페이지, 결과 페이지 HTML
│   └── migrations/
│
├── product/                   # [App] 제품 추천 및 정보 관리
│   ├── models.py              # 화장품 정보, 컬러 타입과의 매핑 관계
│   ├── views.py               # 제품 목록 및 상세 페이지 로직
│   ├── fixtures/              # 초기 화장품 데이터 (Initial Data)
│   ├── templates/
│   │   └── product/
│   │       └── index.html     # 제품 추천 메인 페이지
│   └── migrations/
│
└── templates/                 # [Global] 공통 템플릿 (base.html 등)
