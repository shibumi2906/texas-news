Local Entertainment News Platform
Technical Specification
Version: 1.0
Initial market: United States
Initial portal: Texas
Status: Implementation specification
Primary implementation agent: Codex
________________


1. Purpose
Разработать production-oriented платформу локальных entertainment-news порталов.
Платформа должна позволять запускать отдельные новостно-развлекательные сайты для:
* штатов;
* городов;
* metro areas;
* регионов;
* стран.
Первый портал:
Texas Entertainment Portal
В дальнейшем та же платформа должна поддерживать:
* Dallas;
* Houston;
* Austin;
* San Antonio;
* другие города США;
* другие штаты США;
* Японию;
* Китай;
* другие рынки.
Каждый портал:
* работает на собственном домене;
* имеет собственную локальную идентичность;
* имеет собственные branding settings;
* имеет собственную географию;
* может иметь собственный набор категорий;
* может иметь собственные языки;
* имеет собственные ranking settings;
* имеет собственные advertising settings;
* использует общий backend;
* использует общий frontend;
* использует общую AI-инфраструктуру.
Платформа строится вокруг модели:
Content + Entity + Geography + Audience
а не вокруг простой сущности Article.
________________


2. Product Positioning
Платформа объединяет:
Entertainment Media + Local News + Social Content + Community + AI
Основные тематические направления:
* Sports;
* Movies & TV;
* Celebrity;
* Music;
* Gaming;
* Viral;
* Animation;
* Memes;
* Travel;
* Food;
* Lifestyle;
* Events;
* Local Entertainment.
Основные критерии контента:
* интерес;
* визуальность;
* локальная релевантность;
* обсуждаемость;
* возвращаемость;
* цитируемость;
* вирусность.
________________


3. Scope Boundary
3.1 Existing News Integrator
Отдельно уже существует система сбора и подготовки новостей.
Она отвечает за:
* RSS;
* crawling;
* получение контента из источников;
* получение metadata;
* загрузку исходного материала;
* первичную normalization;
* parsing;
* source tracking;
* первичную AI-обработку контента;
* duplicate detection;
* story clustering;
* entity extraction;
* geography extraction;
* preliminary taxonomy;
* базовый translation/enrichment;
* формирование canonical content package.
Новая Site Platform не должна дублировать эту функциональность.
________________


4. System Context
Основной поток:
NEWS SOURCES
      │
      ▼
EXISTING NEWS INTEGRATOR
      │
      ▼
CONTENT AI / ENRICHMENT
      │
      ▼
CANONICAL NEWS PACKAGE
      │
      ▼
SITE PLATFORM API
      │
      ├── Content
      ├── Media
      ├── Portal / Tenant
      ├── Geography
      ├── Taxonomy
      ├── Entities
      ├── Feed
      ├── Trending
      ├── Search
      ├── Users
      ├── Community
      ├── Recommendations
      ├── Localization
      ├── SEO
      ├── Advertising
      ├── Notifications
      └── Analytics
      │
      ▼
WEB / MOBILE WEB / FUTURE APP


________________


5. First Production Target
Первой реализацией платформы является:
Texas Entertainment Portal
Она должна быть полностью рабочей вертикальной системой:
Integrator
    ↓
Content ingestion
    ↓
PostgreSQL
    ↓
Content publication
    ↓
Texas portal
    ↓
Homepage
    ↓
Category / Topic / Geography
    ↓
Story page
    ↓
Search
    ↓
Analytics events
    ↓
Admin


Первая production-версия не обязана включать все функции, описанные далее.
Архитектура должна позволять их добавить без фундаментального переписывания системы.
________________


6. Implementation Principles
6.1 Production-first
Код не должен выглядеть как:
* proof-of-concept;
* demo;
* prototype-only architecture;
* collection of scripts;
* LLM wrapper.
Система должна иметь:
* стабильную архитектуру;
* миграции;
* тесты;
* структурированное логирование;
* обработку ошибок;
* configuration management;
* observability;
* security boundaries.
________________


6.2 Modular Monolith First
Первая версия реализуется как:
modular monolith
а не набор микросервисов.
Причина:
* проще разработка;
* проще deployment;
* проще локальный запуск;
* проще транзакции;
* меньше operational complexity.
Но модули должны иметь чёткие интерфейсы, чтобы в будущем их можно было выделять в отдельные сервисы.
________________


7. Technology Stack
7.1 Repository
Использовать monorepo.
/news-platform
    /apps
        /web
        /api
    /packages
        /shared
    /infra
    /docs
    /scripts
    SPEC.md
    README.md


________________


8. Frontend Stack
Использовать:
* Next.js;
* TypeScript;
* React;
* App Router;
* server-side rendering;
* server components там, где это оправдано;
* responsive design;
* semantic HTML;
* CSS architecture без привязки бизнес-логики к UI library.
Frontend должен поддерживать:
* desktop;
* tablet;
* mobile web.
Основной deployment target:
web browser
Native mobile application не входит в первую реализацию.
________________


9. Backend Stack
Использовать:
* Python 3.12+;
* FastAPI;
* Pydantic v2;
* SQLAlchemy 2.x;
* Alembic;
* PostgreSQL;
* Redis.
Backend является главным источником бизнес-логики.
Frontend не должен самостоятельно реализовывать:
* ranking;
* access policy;
* publication rules;
* portal routing;
* moderation decisions;
* recommendation algorithms.
________________


10. Database
Primary database:
PostgreSQL
Использовать PostgreSQL для:
* content;
* users;
* portals;
* taxonomy;
* geography;
* entities;
* community;
* engagement;
* configuration;
* editorial data;
* AI metadata.
Redis использовать только для:
* cache;
* rate limiting;
* short-lived distributed locks;
* ephemeral feed cache;
* background jobs.
Redis не является authoritative storage.
________________


11. Search
Первая версия:
PostgreSQL Full Text Search
Архитектура Search Service должна позволять позднее подключить:
* OpenSearch;
* Elasticsearch;
* vector search.
Search abstraction не должна быть жёстко привязана к PostgreSQL.
________________


12. Background Processing
Для background jobs использовать task queue поверх Redis.
Допустимые задачи:
* feed recomputation;
* sitemap generation;
* notifications;
* media processing;
* analytics aggregation;
* AI jobs;
* cache warming.
Business-critical state не должен существовать только внутри очереди.
________________


13. Deployment
Первая версия должна поддерживать Docker.
Обязательные контейнеры:
web
api
worker
postgres
redis


Для локальной разработки использовать:
docker compose


Production deployment не должен зависеть от Docker Compose.
________________


14. Configuration
Configuration должна читаться из:
* environment variables;
* configuration files;
* database settings, где требуется runtime editing.
Secrets не должны храниться:
* в repository;
* в frontend;
* в source code.
________________


15. Domain Architecture
Backend разделяется на модули:
platform
├── content
├── media
├── portals
├── geography
├── taxonomy
├── entities
├── ingestion
├── editorial
├── feeds
├── trending
├── recommendations
├── search
├── users
├── community
├── engagement
├── localization
├── moderation
├── advertising
├── notifications
├── seo
├── analytics
└── ai


Каждый модуль должен иметь:
domain
application
infrastructure
api


Разрешается упрощённая структура, если границы модулей остаются явными.
________________


16. Core Entities
Минимальный domain model:
Portal
ContentItem
ContentVersion
MediaAsset
Source
Category
Topic
Entity
ContentEntity
GeographyNode
ContentGeography
Translation
User
UserProfile
UserInterest
Comment
Reaction
Follow
Save
BehaviorEvent
FeedItem
AIExecution
PromptVersion


________________


17. Portal
Portal представляет отдельный сайт.
Основные поля:
id
slug
name
domain
status
primary_geography_id
default_language
supported_languages
timezone
branding
logo
categories
ranking_settings
ai_settings
advertising_settings
seo_settings
feature_flags
created_at
updated_at


Примеры:
texas
dallas
houston
austin


________________


18. Multi-Tenant Rules
Все portal-specific сущности должны быть привязаны к portal_id, где это необходимо.
Запросы не должны случайно возвращать данные другого портала.
Portal context определяется через:
1. hostname;
2. explicit internal portal ID;
3. admin context.
Frontend не должен доверять portal_id, переданному пользователем, без backend validation.
________________


19. ContentItem
ContentItem — центральная публикационная сущность.
Типы:
article
image
gallery
meme
video
short
live
event


Основные поля:
id
external_id
content_type
status
source_id
original_url
original_language
primary_language
title
subtitle
description
body
publication_time
original_publication_time
first_seen_at
updated_at
created_at
canonical_content_hash
story_cluster_id
author
metadata
seo


________________


20. Content Lifecycle
Использовать explicit state machine.
Допустимые состояния:
received
processing
ready
scheduled
published
unpublished
retracted
archived
deleted
failed


Основной lifecycle:
received
   ↓
processing
   ↓
ready
   ↓
published


Дополнительно:
ready → scheduled → published
published → unpublished
published → retracted
any → failed
unpublished → published
deleted → restore


Hard delete запрещён для обычной editorial операции.
________________


21. Content Versioning
Изменения материала должны быть версионируемыми.
ContentVersion хранит:
id
content_item_id
version_number
source_revision
title
description
body
metadata
created_at
created_by
change_reason


Необходимо различать:
* source update;
* AI enrichment update;
* editor modification;
* correction;
* translation modification.
________________


22. Correction / Retraction
Integrator должен иметь возможность сообщить:
created
updated
corrected
retracted
deleted


Это значения поля operation в schema 1.1. Операция restored не входит в текущий Integrator contract; editorial restore остаётся Site-side workflow.


Retraction не должен физически удалять историю публикации.
При retraction:
* публикация больше не показывается в обычных feeds;
* URL может сохраняться;
* backend может показывать retraction notice;
* editorial history сохраняется.
________________


23. MediaAsset
Основные типы:
image
video
audio
thumbnail
poster
document


Поля:
id
content_item_id
type
source_url
storage_url
mime_type
width
height
duration
size
checksum
copyright
attribution
metadata
status


________________


24. Media Storage
Media abstraction должна позволять использовать:
* local object storage в development;
* S3-compatible storage в production.
Backend не должен зависеть от конкретного cloud provider.
Frontend получает media через normalized media URL.
________________


25. Geography
Использовать hierarchical geography model:
World
Country
State / Province
Metro
City
District


Пример:
World
└── United States
    └── Texas
        └── Dallas–Fort Worth
            └── Dallas


________________


26. GeographyNode
Поля:
id
type
name
slug
country_code
parent_id
timezone
latitude
longitude
metadata


Один ContentItem может быть связан с несколькими GeographyNode.
________________


27. ContentGeography
Связь:
content_item_id
geography_id
relationship_type
confidence
source


relationship_type:
primary
mentioned
event_location
person_origin
team_location
venue_location


________________


28. Taxonomy
Необходимо различать:
Category
редакционная крупная категория:
Sports
Movies
Gaming
Celebrity
Music
Viral
Travel
Food
Local


Topic
более конкретная тема:
NBA
Marvel
Country Music
Anime
Dallas Nightlife


Descriptor
семантический признак:
breaking
viral
controversy
interview
review
trailer
rumor


________________


29. Entities
Entity представляет именованный объект.
Типы:
person
organization
sports_team
movie
tv_show
game
artist
venue
event
brand
franchise
location
other


Поля:
id
type
canonical_name
slug
aliases
external_ids
metadata


________________


30. Knowledge Graph
Начальная реализация knowledge graph строится поверх relational tables.
Не вводить отдельную graph database на первом этапе.
Связи:
Content ↔ Entity
Entity ↔ Entity
Entity ↔ Geography
Content ↔ Topic


Graph database может быть добавлена позже.
________________


31. Integrator Contract
Integrator и Site Platform взаимодействуют через versioned HTTP API.
Основной endpoint:
POST /internal/v1/ingestion/content


Принимается:
CanonicalNewsPackageEnvelope


Wire-level schema, validation rules и delivery semantics нормативно определены в NEWS_INTEGRATOR_INTERFACE.md. Этот документ не создаёт альтернативный ingestion contract.


Поддерживаются ровно schema versions:
* 1.0;
* 1.1.


Schema 1.1 является additive extension к 1.0. Unsupported schema versions отклоняются до persistence.


________________


32. CanonicalNewsPackageEnvelope
Обязательные identity и payload fields:
* schema_version;
* package_id;
* package_version;
* instance_id;
* event_id;
* content;
* sources.


Schema 1.1 добавляет без удаления полей 1.0:
* operation;
* revision_reason;
* typed categories и topics;
* geographies;
* typed media;
* ai_provenance;
* richer source provenance.


Site Platform должна потреблять canonical content, language_versions, source provenance, categories, topics, geographies, media и AI provenance. Legacy taxonomy и regions сохраняются для совместимости с 1.0 consumers.


Точная структура полей и validation rules определены в NEWS_INTEGRATOR_INTERFACE.md и generated canonical schema; SPEC.md не дублирует полную payload schema.


________________


33. Lifecycle Operations
В schema 1.1 поле operation принимает только:
* created;
* updated;
* corrected;
* retracted;
* deleted.


Initial package использует created и package_version 1. Updated, corrected, retracted и deleted создают новые immutable package versions. Correction требует replacement content и reason. Retraction и deletion требуют reason; deletion является tombstone, а предыдущие версии сохраняются.


Операция content.restored отсутствует в actual Integrator contract и не должна приниматься как wire-level lifecycle operation.


________________


34. Package Identity and Idempotency
package_id является стабильной logical identity пакета.
package_version является monotonically increasing positive integer.
event_id сохраняет identity события, но delivery idempotency определяется immutable package identity/version pair.


Каждый delivery содержит:
Idempotency-Key: <package_id>:<package_version>


Повторная доставка той же package version:
* не создаёт duplicate IncomingPackageVersion;
* не создаёт duplicate Site-side content version;
* возвращает успешный idempotent acknowledgement.
________________


35. Package Version Ordering and Receiver Persistence
Каждая принятая package version сохраняется как immutable IncomingPackageVersion. IncomingPackage хранит latest_version для текущего представления пакета.


latest_version продвигается только если incoming package_version больше текущей. Late replay старой версии может быть сохранён или подтверждён idempotently, но не должен регрессировать current state.


Package versions не изменяются in place. Receiver persistence и обновление latest pointer выполняются transactionally.


________________


36. Authentication Between Integrator and Platform
Использовать request signing.
Headers:
Idempotency-Key: <package_id>:<package_version>
X-Integrator-Instance-Id: <integrator UUID>
X-Signing-Key-Id: <key identifier>
X-Timestamp: <UTC timestamp>
X-Signature: <hex HMAC-SHA256>


Signature покрывает request timestamp и exact request body. Site Platform должна:
* выбрать verification secret по X-Signing-Key-Id;
* проверить timestamp в пределах configured clock-skew window;
* проверить HMAC-SHA256 в constant time;
* поддерживать active и previous keys во время rotation window;
* отклонять unknown и retired key IDs.


Rotation выполняется с перекрытием: новый key устанавливается как active, предыдущий временно сохраняется как previous, после подтверждения доставки previous key удаляется. Secrets не должны попадать в responses, audit details, logs или metrics.


________________


37. Delivery Acknowledgement
Successful non-empty response использует IncomingPackageReceipt и должен содержать совпадающие с request:
* package_id;
* package_version;
* status.


Malformed или inconsistent non-empty acknowledgement считается delivery failure. Для совместимости со старыми Site receivers Integrator также принимает empty successful 2xx response.


Site Platform возвращает корректные HTTP statuses, чтобы Integrator мог отличать accepted delivery, invalid/non-retryable request, rate limiting и retryable server failure.


________________


38. Retry and Dead Letter Responsibility
Integrator владеет:
* delivery retries;
* durable retry attempt budget;
* exponential delivery backoff;
* dead-letter state;
* operator inspection;
* manual retry/requeue.


Site Platform не реализует независимый delivery DLQ для incoming packages и не повторяет invalid ingestion internally. Её обязанность — вернуть корректный HTTP response для классификации результата Integrator-ом.
________________


39. Replay and Backfill
Replay/backfill инициируется на стороне Integrator и повторно отправляет существующие immutable package versions. Replay:
* не создаёт и не изменяет canonical packages;
* сохраняет исходные package_id и package_version;
* сохраняет исходный wire-level Idempotency-Key;
* использует тот же signed CanonicalNewsPackageEnvelope;
* является idempotent для Site receiver;
* не позволяет старым версиям регрессировать latest state.


Отдельный Site-side ingestion/backfill endpoint не требуется. Integrator-side replay administration и status API описаны в NEWS_INTEGRATOR_INTERFACE.md.
________________


40. Responsibility Boundary
Integrator владеет source ingestion, parsing, normalization, canonical package creation, package versioning, source provenance, enrichment, clustering, taxonomy/geography/media extraction и outbound signed delivery.


Site Platform владеет receipt validation, immutable incoming package persistence, mapping в Site domain, editorial workflows, publication, feeds и distribution.


Function
	Integrator
	Site Platform
	AI Service
	crawling
	yes
	no
	no
	RSS
	yes
	no
	no
	parsing
	yes
	no
	no
	source normalization
	yes
	no
	no
	base deduplication
	yes
	no
	optional
	story clustering
	yes
	consume
	optional
	entity extraction
	yes
	consume/edit
	execution
	geography extraction
	yes
	consume/edit
	execution
	base translation
	yes
	consume
	execution
	content classification
	yes
	consume/edit
	execution
	portal routing
	no
	yes
	optional
	feed ranking
	no
	yes
	optional
	trending
	no
	yes
	semantic signal
	personalization
	no
	yes
	optional
	AI Chat
	no
	yes
	execution
	AI Search
	no
	yes
	execution
	moderation decision
	no
	yes
	classification only
	________________


41. Feed Service
Backend формирует готовые feeds.
Основные feeds:
Home
Latest
Trending
Local
For You
Following
Sports
Movies
Gaming
Celebrity
Music
Viral
Video
Shorts
Community


Frontend не строит ranking самостоятельно.
________________


42. Feed API
Пример:
GET /api/v1/feed/home
GET /api/v1/feed/latest
GET /api/v1/feed/trending
GET /api/v1/feed/category/{slug}
GET /api/v1/feed/local/{geography_slug}


Обязательные параметры:
cursor
limit
language


Использовать cursor pagination.
Не использовать offset pagination для больших live feeds.
________________


43. Trending Engine
Trending не должен зависеть от LLM.
Начальная scoring model использует:
impressions
clicks
CTR
views
view growth
comments
likes
shares
saves
watch time
completion
freshness
geography


Пример концептуальной формулы:
trend_score =
engagement_velocity
× freshness_decay
× local_relevance
× content_quality


Конкретные веса должны находиться в конфигурации.
________________


44. Recommendations
Первая recommendation system использует:
categories
topics
entities
geography
user history
engagement
follows


Следующие этапы:
embeddings
semantic similarity
collaborative filtering
AI reranking


LLM не должна быть единственным recommendation engine.
________________


45. Behavioral Events
Собирать минимум:
impression
click
content_open
scroll
video_start
watch_time
completion
like
reaction
comment
share
save
follow
search
ai_query


________________


46. BehaviorEvent
Поля:
id
portal_id
user_id
anonymous_id
session_id
event_type
content_id
entity_id
geography_id
timestamp
properties


Не помещать потенциально чувствительные данные в properties без необходимости.
________________


47. Anonymous Users
Anonymous user может:
* читать;
* смотреть;
* искать;
* открывать comments;
* пользоваться basic navigation.
Anonymous user должен иметь anonymous session identifier.
________________


48. Authentication
Login требуется для:
* comment;
* reply;
* like;
* reaction;
* save;
* follow;
* personalised feed;
* notification subscriptions.
Authentication architecture должна позволять подключить:
* email;
* Google;
* Apple;
* другие providers.
________________


49. Community
Поддержать:
comments
replies
likes
reactions
reports
quote
pin
moderation
ranking


Comment должен иметь:
id
portal_id
content_id
user_id
parent_id
body
status
created_at
updated_at
score


________________


50. Comment Status
visible
pending
hidden
removed
spam
blocked


________________


51. Moderation
LLM не принимает окончательное решение о блокировке.
AI Moderation возвращает signals:
spam_probability
scam_probability
toxicity_probability
abuse_probability
suspicious_link_probability


Backend moderation rules принимают решение.
________________


52. Search
Classic search должен поддерживать:
* keyword;
* content;
* entities;
* location;
* categories;
* date;
* content type.
Пример:
GET /api/v1/search?q=mavericks


________________


53. AI Search
AI Search добавляется поверх обычного search/retrieval.
Пример:
What happened with the Mavericks this week?
What concerts are happening in Austin this weekend?


AI не должен отвечать только на основе внутренних знаний модели.
Для platform-related questions он должен получать context из внутренней базы.
________________


54. AI Architecture
Все AI-вызовы проходят через:
AI Service
    ↓
Task Manager
    ↓
Prompt Manager
    ↓
Model Router
    ↓
Provider Adapter
    ↓
External AI Provider / Gateway


________________


55. AI Service Boundary
Остальные компоненты не должны знать:
Gemini
OpenAI
Claude
Grok
DeepSeek
Qwen
OpenRouter


Они должны запрашивать:
extract_entities
moderate_comment
translate_content
summarize_story
answer_story_question


________________


56. AI Task Definition
Каждая задача имеет configuration:
task_name
primary_model
fallback_models
allowed_providers
max_cost
max_input_tokens
max_output_tokens
timeout
max_retries
reasoning_level
response_schema
prompt_version
cache_policy


________________


57. AI Gateway
Первоначально допускается внешний aggregator, например gateway типа OpenRouter.
Но он всегда скрыт за:
GatewayAdapter


В будущем возможны:
OpenRouterAdapter
OpenAIAdapter
GoogleAdapter
AnthropicAdapter
XAIAdapter
LocalModelAdapter


________________


58. Model Router
Model Router выбирает модель на основании:
* task;
* language;
* modality;
* cost;
* latency;
* required structured output;
* model availability;
* model quality;
* configured policy.
________________


59. AI Fallback
Fallback применяется при:
* timeout;
* provider error;
* rate limit;
* unavailable model;
* invalid structured output;
* schema validation error.
Пример:
primary
   ↓ error
fallback_1
   ↓ error
fallback_2


Fallback configuration является task-specific.
________________


60. AI Structured Output
Backend AI jobs должны по возможности использовать machine-readable schema.
Пример:
{
  "category": "sports",
  "country": "US",
  "state": "Texas",
  "city": "Dallas",
  "entities": [
    "Dallas Mavericks",
    "NBA"
  ],
  "virality_score": 0.82
}


Результат валидируется Pydantic schema.
________________


61. Invalid AI Response
При invalid structured output:
validate
 ↓ fail
repair
 ↓ fail
retry
 ↓ fail
fallback
 ↓ fail
mark execution failed


Retry не должен быть бесконечным.
________________


62. AI Cache
AI cache key должен учитывать:
content_hash
task
model
prompt_version
language
schema_version


Одинаковый deterministic AI task над неизменившимся контентом не должен повторно вызываться без причины.
________________


63. Prompt Management
Prompts не должны быть жёстко разбросаны по application code.
Использовать:
PromptDefinition
PromptVersion


Поля:
task
version
template
status
created_at
created_by
notes


________________


64. AI Observability
Для каждого вызова сохранять:
execution_id
task
provider
model
gateway
latency
input_tokens
output_tokens
estimated_cost
success
error_type
retry_count
fallback_used
content_id
portal_id
prompt_version
created_at


________________


65. AI Cost Control
Для каждой AI task задаётся:
* max cost per call;
* allowed models;
* maximum tokens;
* maximum retry count;
* timeout;
* reasoning policy.
Дорогие reasoning models не использовать для:
* category assignment;
* city extraction;
* simple classification;
* basic moderation.
________________


66. AI A/B Testing
Архитектура должна позволять:
80% production model
10% model A
10% model B


Сравнивать:
* quality;
* cost;
* latency;
* structured output success;
* editorial evaluation;
* downstream user engagement.
A/B testing не входит в первую implementation phase.
________________


67. AI Chat
AI Chat должен поддерживать:
What's trending?
What happened today?
What's happening near me?
What should I watch?
Why is this important?
Who is this person?
Show related stories.


Ответ должен ссылаться на platform content.
________________


68. AI Digest
Поддерживаемые будущие сценарии:
Top 5 today
Morning digest
Evening digest
Overnight
Sports recap
Local recap
Topic digest
Personalised digest


________________


69. Multilingual Content
Один ContentItem может иметь:
Original
EN
ES
JA
ZH
...


Нужно различать:
original_language
translation_language
translation_source
translation_status
reviewed_by


________________


70. Translation Status
machine
reviewed
editorial
outdated
failed


Изменение original content должно помечать старые translations как потенциально outdated.
________________


71. Localization
Portal имеет:
default_language
supported_languages


User может иметь:
preferred_language


Выбор представления:
user language
    ↓
portal language
    ↓
original language


________________


72. SEO
Backend отвечает за:
* slug;
* canonical URL;
* metadata;
* OpenGraph;
* schema.org;
* News Sitemap;
* hreflang;
* redirects;
* robots policy.
AI может предлагать SEO metadata.
Окончательная SEO-логика принадлежит backend.
________________


73. URL Structure
Пример:
/
 /sports
 /movies
 /gaming
 /viral
 /local
 /video
 /shorts
 /story/{slug}
 /topic/{slug}
 /entity/{slug}
 /place/{slug}
 /search


URL structure должна быть portal-aware.
________________


74. Slugs
Slug должен быть:
* stable;
* lowercase;
* URL-safe;
* unique within required namespace.
При изменении slug должен создаваться redirect.
________________


75. Advertising
Advertising является отдельным backend module.
Сущности:
AdCampaign
AdPlacement
AdCreative
AdTargeting
AdImpression
AdClick


Targeting может учитывать:
portal
geography
language
category
content type


Первая версия может использовать feature flag:
advertising_enabled=false


________________


76. Notifications
Будущие каналы:
* web push;
* mobile push;
* email.
User может follow:
* city;
* team;
* person;
* movie;
* game;
* event;
* topic.
Notification subsystem не входит в initial production scope.
________________


77. Editorial Admin
Admin должен поддерживать:
* content list;
* content search;
* publish;
* unpublish;
* schedule;
* retract;
* restore;
* edit title;
* edit description;
* edit body;
* replace media;
* change category;
* change geography;
* edit descriptors;
* set Hero;
* pin;
* force Trending;
* merge;
* exclude.
________________


78. Editorial Audit Log
Каждое важное admin действие должно сохранять:
actor
action
entity_type
entity_id
before
after
timestamp
reason


________________


79. AI Admin
В дальнейшем admin должен иметь:
AI Models
AI Tasks
Routing
Fallback
Usage
Cost
Latency
Errors
A/B Tests
Prompts
Model Quality


Первая версия требует backend configuration, но не обязательно полноценный UI для всех этих функций.
________________


80. Visual Product Principles
UI должен быть:
* крупным;
* современным;
* визуальным;
* эмоциональным;
* entertainment-first;
* не перегруженным.
Не использовать homepage из десятков одинаковых маленьких cards.
Основной принцип:
меньше объектов → крупнее объекты → сильнее фокус
________________


81. Focus UX
Предпочтительная навигация:
overview
  ↓
focus
  ↓
detail
  ↓
context
  ↓
related


Допустимы:
* expanded cards;
* fullscreen media;
* horizontal sections;
* sticky sections;
* controlled animation;
* smooth scroll transitions.
UX не должен ухудшать:
* accessibility;
* SEO;
* Core Web Vitals.
________________


82. Homepage
Обязательные initial блоки:
Hero
* основной материал;
* large media;
* headline;
* description;
* content type;
* category;
* geography.
Trending
* быстро растущий контент.
Categories
Минимум:
Sports
Movies
Gaming
Celebrity
Music
Viral
Travel
Food
Local


Video / Shorts
Отдельный визуальный блок.
________________


83. Story Page
Story page должен иметь:
* headline;
* subtitle;
* source;
* publication time;
* update time;
* primary media;
* body;
* categories;
* entities;
* geography;
* related content;
* share controls.
Comments и Ask AI добавляются соответствующими фазами.
________________


84. Performance Requirements
Начальные targets:
Backend API:
P95 read latency < 300 ms


для cacheable standard read endpoints без external AI call.
Homepage server response:
target < 1 second backend processing


AI requests не входят в обычный page render critical path.
________________


85. Scalability Baseline
Архитектура должна нормально поддерживать минимум:
100,000+ ContentItems
1,000,000+ BehaviorEvents/day
multiple portals
multiple languages


Эти значения являются engineering baseline, а не коммерческим прогнозом.
________________


86. Caching
Допустимое кеширование:
* portal config;
* homepage feed;
* trending;
* category feeds;
* entity pages;
* search suggestions;
* AI results.
Кеш должен иметь explicit TTL и invalidation strategy.
________________


87. Cache Invalidation
Content publication/update/retraction должны инвалидировать связанные:
* homepage cache;
* category cache;
* geography cache;
* story cache;
* entity cache при необходимости.
________________


88. Security
Обязательные меры:
* HTTPS;
* secure cookies;
* CSRF protection where applicable;
* XSS protection;
* parameterized SQL;
* input validation;
* rate limiting;
* authentication;
* authorization;
* audit logs;
* secrets management.
________________


89. Authorization
Минимальные роли:
user
moderator
editor
admin
system


________________


90. Rate Limiting
Rate limits необходимы минимум для:
* login;
* comments;
* reactions;
* search;
* AI Chat;
* AI Search;
* ingestion API.
________________


91. Content Sanitization
HTML content от Integrator или editor должен быть sanitized.
Запрещено напрямую рендерить arbitrary source HTML.
________________


92. Privacy
Не собирать user data без функциональной необходимости.
Behavior analytics должна поддерживать anonymous identifier.
Не хранить:
* raw passwords;
* unnecessary personal information;
* provider secrets в database plaintext, если этого можно избежать.
________________


93. Logging
Использовать structured logs.
Каждый request должен иметь:
request_id


В distributed/background context использовать:
correlation_id


________________


94. Metrics
Минимальные metrics:
* request count;
* error rate;
* API latency;
* queue size;
* queue failures;
* ingestion rate;
* published content;
* DB connection usage;
* cache hit rate;
* AI calls;
* AI cost;
* AI errors.
________________


95. Error Tracking
Production environment должен иметь integration point для error tracking system.
Implementation не должна жёстко зависеть от одного SaaS provider.
________________


96. Health Checks
Endpoints:
GET /health/live
GET /health/ready


Readiness проверяет:
* database;
* Redis;
* critical dependencies.
________________


97. Database Migrations
Все изменения schema выполняются через Alembic migrations.
Нельзя менять production schema вручную как часть normal workflow.
________________


98. Backups
Production PostgreSQL должен иметь:
* automated backups;
* retention policy;
* restore procedure.
Object storage должен иметь соответствующую durability strategy.
________________


99. Testing Strategy
Обязательны:
unit tests
integration tests
API tests
repository tests
migration tests
frontend component tests
end-to-end smoke tests


________________


100. Backend Test Rules
Критические domain rules должны тестироваться без HTTP layer.
Например:
* lifecycle transitions;
* ingestion idempotency;
* revision ordering;
* portal isolation;
* publication rules;
* moderation rules.
________________


101. Integration Tests
Использовать настоящий PostgreSQL test instance.
Не заменять PostgreSQL SQLite при тестировании SQL-specific functionality.
________________


102. End-to-End Tests
Минимальный smoke flow:
create/import content
    ↓
publish
    ↓
open Texas homepage
    ↓
open story
    ↓
open category
    ↓
search story


________________


103. Development Environment
Проект должен запускаться командой, описанной в README.
Желательная схема:
docker compose up


и отдельные команды для:
backend tests
frontend tests
migrations
lint
type check


________________


104. Code Quality
Backend:
* Ruff;
* formatting;
* type hints;
* mypy или эквивалентный strict type checking на важных модулях.
Frontend:
* ESLint;
* TypeScript strict mode;
* formatting.
________________


105. API Conventions
Основной prefix:
/api/v1


Internal APIs:
/internal/v1


Не смешивать public и internal endpoints.
________________


106. API Response
Использовать стабильные typed responses.
Error response:
{
  "error": {
    "code": "CONTENT_NOT_FOUND",
    "message": "Content item was not found",
    "request_id": "..."
  }
}


________________


107. Dates
Все backend timestamps хранить в UTC.
Frontend отображает время согласно:
Portal timezone
или
User timezone


________________


108. IDs
Internal identifiers:
UUID


External Integrator IDs хранятся отдельно.
Никогда не считать Integrator ID внутренним database primary key.
________________


109. Feature Flags
Feature flags должны существовать минимум для:
community
ai_chat
ai_search
recommendations
personalization
shorts
advertising
notifications
multilingual


________________


110. Initial Texas Portal Configuration
Первый tenant:
slug: texas
country: US
state: Texas
default_language: en
supported_languages:
  - en


Испанский должен быть предусмотрен архитектурно, но не обязан входить в самый первый release.
________________


111. Initial Categories
Создать:
Sports
Movies & TV
Celebrity
Music
Gaming
Viral
Travel
Food
Lifestyle
Events
Local


________________


112. Initial Content Types
Первая production версия обязана полноценно поддерживать:
article
image
video


Архитектурно также создать enum:
gallery
meme
short
live
event


Их полноценный UX реализуется позднее.
________________


113. Phase-Based Implementation
Codex должен реализовывать проект строго по фазам.
Запрещено реализовывать функциональность последующих фаз, если она не требуется для текущей фазы.
Каждая фаза заканчивается:
1. working code;
2. migrations;
3. tests;
4. README update;
5. successful local run;
6. кратким implementation report.
________________


114. Phase 0 — Repository and Infrastructure
Scope
Создать:
* monorepo;
* backend skeleton;
* frontend skeleton;
* PostgreSQL;
* Redis;
* Docker configuration;
* environment configuration;
* health checks;
* linting;
* testing infrastructure.
Acceptance Criteria
Должны работать:
docker compose up


GET /health/live
GET /health/ready


Frontend должен открываться.
Backend должен подключаться к PostgreSQL.
Alembic migration должна выполняться.
________________


115. Phase 1 — Core Domain
Реализовать:
Portal
GeographyNode
Category
Topic
Entity
Source
ContentItem
ContentVersion
MediaAsset


Добавить migrations.
Создать Texas portal seed.
Создать basic repository/application services.
Acceptance Criteria
Можно:
* создать content;
* получить content;
* создать geography;
* связать content с geography;
* связать content с categories/entities.
Не создавать пока public homepage.
________________


116. Phase 2 — Integrator Ingestion
Реализовать:
/internal/v1/ingestion/content


Добавить:
* приём CanonicalNewsPackageEnvelope schema 1.0 и 1.1;
* rejection unsupported schema versions before persistence;
* HMAC-SHA256 authentication и signing-key rotation semantics из раздела 36;
* package identity/version idempotency;
* immutable IncomingPackageVersion persistence;
* latest-version ordering без regression при late replay;
* lifecycle operations created, updated, corrected, retracted и deleted;
* IncomingPackageReceipt acknowledgement с empty successful 2xx compatibility;
* mapping content, language versions, sources/provenance, categories, topics, geographies, media и AI provenance;
* compatibility с legacy taxonomy и regions;
* payload validation;
* ingestion logs.


NEWS_INTEGRATOR_INTERFACE.md является нормативным источником wire-level payload, signing, acknowledgement, replay и compatibility semantics. Site Platform не реализует отдельный incoming delivery DLQ или специальный backfill endpoint.
Acceptance Criteria
Повтор package_id/package_version не создаёт duplicate package или content version.
Каждая принятая version сохраняется immutably.
Old package_version не регрессирует latest state.
Late replay подтверждается idempotently.
Retraction и deletion сохраняют prior versions.
Invalid signature, timestamp или signing key отклоняется.
Unsupported schema_version отклоняется до persistence.
________________


117. Phase 3 — Editorial Publication
Реализовать:
* content lifecycle;
* publish;
* unpublish;
* schedule;
* restore;
* retract;
* editorial edits;
* audit log.
Создать начальный admin API.
Полноценный красивый admin frontend пока не требуется.
________________


118. Phase 4 — Texas Web Portal
Реализовать production frontend:
* Texas homepage;
* header/navigation;
* Hero;
* Trending placeholder based on published feed;
* category sections;
* story page;
* category page;
* responsive layout;
* SEO metadata;
* canonical URLs.
Acceptance Criteria
Реальный материал из Integrator проходит:
Integrator
→ ingestion
→ database
→ publication
→ Texas homepage
→ story page


Это первый полноценный vertical slice продукта.
________________


119. Phase 5 — Feeds and Trending
Реализовать:
Latest
Home
Category
Local
Trending


Добавить:
* cursor pagination;
* cache;
* engagement counters;
* initial trending algorithm.
________________


120. Phase 6 — Search
Реализовать:
* PostgreSQL FTS;
* keyword search;
* entity search;
* geography filtering;
* category filtering;
* date filtering.
Создать abstraction для будущего OpenSearch.
________________


121. Phase 7 — Analytics and Behavioral Events
Реализовать:
impression
click
content_open
scroll
video_start
watch_time
completion
share
search


Добавить aggregation pipeline для Trending.
________________


122. Phase 8 — Users and Community
Реализовать:
* authentication;
* user profile;
* comment;
* reply;
* like;
* reactions;
* report;
* save;
* follow;
* moderation status.
________________


123. Phase 9 — Recommendations and Personalization
Добавить:
For You
Following
user interests
entity affinity
category affinity
geography affinity
behavioral scoring


LLM не использовать как основной recommendation algorithm.
________________


124. Phase 10 — AI Service
Создать:
Task Manager
Prompt Manager
Model Router
Provider Adapter
Fallback
Structured Output Validator
AI Cache
Cost Tracking
AI Observability


Первая AI task должна быть небольшой и хорошо тестируемой.
Например:
story_summary


Не начинать одновременно с десяти AI функций.
________________


125. Phase 11 — AI Search and AI Chat
После готовности Search и AI Service добавить:
AI Search
Ask about this story
What's trending?
What happened today?


Использовать retrieval из platform database.
________________


126. Phase 12 — Multilingual
Добавить:
* Translation entity;
* EN/ES;
* hreflang;
* language switch;
* translated routes;
* portal language configuration.
Первый дополнительный язык Texas portal:
Spanish
________________


127. Phase 13 — Extended Media UX
Добавить полноценные:
gallery
meme
short
event
live


Shorts UX:
* vertical;
* fullscreen;
* autoplay;
* reactions;
* comments;
* share;
* save;
* related.
________________


128. Phase 14 — Advanced Admin / AI Admin
Добавить UI:
* AI models;
* tasks;
* model routing;
* fallback;
* cost;
* latency;
* errors;
* prompt versions;
* A/B tests.
________________


129. Phase 15 — Advertising and Notifications
Добавить:
* placements;
* campaigns;
* targeting;
* tracking;
* notification subscriptions;
* email/web push integration.
________________


130. Definition of Done for Every Phase
Фаза считается законченной только если:
* код реализован;
* migrations включены;
* unit tests проходят;
* integration tests проходят;
* existing tests не сломаны;
* lint проходит;
* type checking проходит;
* local runtime проверен;
* README обновлён;
* новые environment variables документированы;
* нет TODO, скрывающих обязательную функциональность текущей фазы.
________________


131. Codex Working Rules
Codex должен:
1. Перед реализацией прочитать SPEC.md.
2. Определить текущую фазу.
3. Не реализовывать будущие фазы без необходимости.
4. Сохранять существующую архитектуру.
5. Не заменять выбранный stack без явного указания.
6. Не добавлять cloud services без необходимости.
7. Не добавлять зависимости только ради удобства.
8. Создавать migrations для schema changes.
9. Добавлять tests одновременно с функциональностью.
10. Проверять runtime после изменений.
11. Не имитировать работу внешнего Integrator внутри Site Platform.
12. Не вызывать LLM напрямую из business modules.
13. Все AI calls направлять через AI Service.
14. Не делать frontend authoritative source бизнес-логики.
15. Не менять interface contracts без обновления документации.
________________


132. Prohibited Architecture Decisions
Без отдельного решения запрещено:
* переходить на microservices;
* добавлять Kubernetes;
* добавлять Kafka;
* добавлять graph database;
* добавлять Elasticsearch/OpenSearch раньше соответствующей необходимости;
* строить собственный crawler;
* переносить Integrator внутрь Site Platform;
* использовать LLM для обычного deterministic ranking;
* использовать LLM для authorization;
* использовать LLM как единственный moderation authority;
* hardcode конкретную AI model в business logic.
________________


133. Architectural Evolution
Разделение на modular monolith не является ограничением дальнейшего масштабирования.
В будущем могут быть выделены:
Feed Service
Search Service
AI Service
Community Service
Analytics Service
Notification Service


Но только при наличии фактической operational необходимости.
________________


134. Future Portals
Запуск нового портала должен в идеале требовать:
Portal configuration
+
branding
+
domain
+
geography
+
category settings
+
language settings
+
ranking settings


а не копирования application source code.
________________


135. Final Architectural Principle
Business layer не должен знать:
"We use Gemini"


Business layer должен знать:
"Execute task: extract_entities"


AI layer самостоятельно выбирает:
model
provider
gateway
cost policy
fallback
prompt


________________


136. Final Product Principle
Система строится вокруг:
Content
+
Entity
+
Geography
+
Audience


AI строится вокруг:
Task
+
Quality
+
Cost
+
Latency


Portal строится вокруг:
Geography
+
Branding
+
Language
+
Ranking
+
Audience


Это должно позволить масштабировать:
* количество порталов;
* количество материалов;
* пользователей;
* страны;
* языки;
* AI providers;
* модели;
* traffic;
без фундаментального переписывания платформы.
________________


137. First Codex Task
После создания репозитория Codex получает только следующую задачу:
Read SPEC.md completely.


Implement Phase 0 only.


Do not start Phase 1 or any later phase.


Create the repository structure, backend and frontend skeleton,
PostgreSQL and Redis development infrastructure, Docker Compose,
configuration handling, Alembic setup, health endpoints,
testing infrastructure, linting and basic README.


Verify the project can be started locally.


Run all available tests and checks.


At the end provide:
1. files created;
2. architecture implemented;
3. commands used for verification;
4. test results;
5. any deviations from SPEC.md.


Do not implement content models, ingestion, AI, feeds,
authentication, community or other future functionality.


________________


138. Completion Criterion for the Entire Platform
Платформа считается архитектурно реализованной, когда существует полноценный end-to-end путь:
External source
→ News Integrator
→ Canonical News Package
→ Site Platform
→ Content Storage
→ Editorial / Publication
→ Feed
→ Texas Portal
→ User Interaction
→ Behavioral Data
→ Ranking / Personalisation
→ Community / Search / AI


при этом запуск нового локального портала не требует форка или копирования основной кодовой базы.
________________


End of Technical Specification
