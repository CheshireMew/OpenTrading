# OpenTrading Frontend

Vue 3 + Vite 前端工程。后端构建完成后会托管 `frontend/dist`，开发期可以单独运行 Vite。

## 常用命令

```bash
npm run dev
npm run sync:contracts
npm run typecheck
npm run build
```

`sync:contracts` 会从后端 FastAPI 路由和 Pydantic schema 生成各业务模块的 `generatedContracts.ts` 以及 `src/api/routes.ts`。这些生成文件不要手写修改；页面状态类型应放在对应业务模块内。
