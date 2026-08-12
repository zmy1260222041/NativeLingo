# Hunyuan3D Pro 从概念四视图生成角色基础网格

> v05 候选建模入口。混元生3D 是**独立的 `ai3d` 服务**，不是 `hunyuan`（对话）服务；
> blender-copilot addon 内置的 `_create_hunyuan_job_official` 仍按旧 `hunyuan` 服务签名，已过时，
> 不可直接用。下面是验证可用的直签路径。**不得把 SecretId/SecretKey 写进本树、.blend、报告或日志。**

## 0. 前置（控制台，主账号）

1. CAM 给调用方子账号关联 `QcloudHunyuanFullAccess`（否则 `AuthFailure.UnauthorizedOperation`）。
2. 在 https://console.cloud.tencent.com/ai3d/ 开通服务并走完后付费（否则
   `ResourceUnavailable.NotExist / 计费状态未知`）。注意：官网 3d.hunyuan.tencent.com 的"开通体验"
   和"领取积分"**不等于** API 计费开通。
3. SecretId/SecretKey 存于仓库外（本项目用 `~/Developer/NativeLingo-survival/混元SecretKey.csv`，
   UTF-8 BOM → 读取用 `encoding="utf-8-sig"`）。

## 1. 唯一源图

使用锁定四视图（共享 `../reference/`，原 v04 契约）：

- `../reference/figure_view_0.png` 正面（主图）
- `…/figure_view_1.png` 左、`…/figure_view_2.png` 背、`…/figure_view_3.png` 右（MultiView）

## 2. 直签提交（绕过过时的 addon 路径）

签名复用 addon 的 `_get_tencent_cloud_sign_headers`，但 service/version/endpoint 用 ai3d：

```python
# service=ai3d → endpoint 自动派生为 ai3d.tencentcloudapi.com
# version=2025-05-13（不是 hunyuan 的 2023-09-01）
headParams = {"Action": "SubmitHunyuanTo3DProJob", "Version": "2025-05-13", "Region": "ap-guangzhou"}
data = {
    "Model": "3.1",                 # 取值仅 "3.0"/"3.1"；产品名 hy-3d-3.1 不是合法参数值
    "ImageBase64": <front b64>,     # 正面做主图
    "MultiViewImages": [            # ViewImage 对象字段：ViewType / ViewImageBase64（不是 View/ImageBase64）
        {"ViewType": "left",  "ViewImageBase64": <view_1 b64>},
        {"ViewType": "back",  "ViewImageBase64": <view_2 b64>},
        {"ViewType": "right", "ViewImageBase64": <view_3 b64>},
    ],
}
headers, endpoint = executor._get_tencent_cloud_sign_headers(
    "POST", "/", headParams, data, "ai3d", "ap-guangzhou", secret_id, secret_key)
requests.post(endpoint, headers=headers, data=json.dumps(data))   # → Response.JobId
```

排坑记录（每条都实测过）：service=`hunyuan` → `计费状态未知`；version=`2023-09-01` 配 service
`hunyuan3d`/`hunyuan` → `InvalidAction`；`Model="hy-3d-3.1"` → 不在 `[3.0, 3.1]`；`MultiViewImages`
字段名 `View`/`ImageBase64` → `UnknownParameter`（正确是 `ViewType`/`ViewImageBase64`）。

## 3. 轮询与下载

```python
headParams = {"Action": "QueryHunyuanTo3DProJob", "Version": "2025-05-13", "Region": "ap-guangzhou"}
requests.post(endpoint, headers=headers, data=json.dumps({"JobId": job_id}))
# Response.Status: RUN → DONE；DONE 后 Response.ResultFile3Ds[].{Url, Type, PreviewImageUrl}
# Type 含 "GLB" 的 Url 即预签名 COS 直链（24h 有效），下载到 hunyuan_raw/
```

积分：单图正面 20、四视图多视图 30（`ResultCreditConsumed`）。

## 4. 干净导入、归一化、渲染

幂等脚本（无头、factory-startup，不扰活体 addon 会话）：

```bash
/Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
  --python art/source/characters/chr_player_juvenile/blender/import_render_hunyuan_v05.py
```

产出：`hunyuan_source/*.blend`、`hunyuan_processed/*_normalized.glb`、
`validation/hunyuan_mv_{ny,px,py,nx}_clay.png`、`hunyuan_import_report.json`。
Gate A IoU：`blender/gate_a_compare_v04_v05.py`（同掩膜法 A/B Rodin v04）。

## 5. 已验证状态（多视图 v3.1）

299,156 顶点 / 500,000 三角面 / 1 个 4096² PBR 材质 / 1.78m / 95,466 非流形边 / 2,227 连通体。
Gate A：均值 IoU 0.619（front 0.778 / left 0.739 / back 0.638 / right 0.321），四视图全面优于
Rodin v04（均值 0.547），且无 Rodin 的尾巴幻觉。剩余 Gate A 雕刻项：单片头冠分三片后掠帆。
