# Asset Manifest

> Last updated: 2026-08-15
> Character pipeline authority: `design/art/character-modeling-standard.md`
> Environment pipeline authority: `design/art/environment-modeling-standard.md`
> Protected file authority: `art/source/characters/ASSET_LOCK_MANIFEST.json`,
> `art/source/environment/ASSET_LOCK_MANIFEST.json`

## Character: Player Juvenile

| Asset ID | Name | Category | Status | Spec File |
|---|---|---|---|---|
| ASSET-001 | Player Juvenile Four-View Concept | 2D Reference | Approved | `design/assets/specs/player-juvenile-assets.md` |
| ASSET-002 | Hunyuan Sculpt Base | 3D Source | Gate A Conditional Pass | `art/source/characters/chr_player_juvenile/source_locked_v05/GATE_A_REVIEW.md` |
| ASSET-003 | `chr_player_juvenile_lod0` | 3D Mesh | Pending Gate A | `design/assets/specs/player-juvenile-assets.md` |
| ASSET-004 | `chr_player_juvenile_lod1` | 3D Mesh | Pending LOD0 | `design/assets/specs/player-juvenile-assets.md` |
| ASSET-005 | `chr_player_juvenile_lod2` | 3D Mesh | Pending LOD0 | `design/assets/specs/player-juvenile-assets.md` |
| ASSET-006 | Player Stylized PBR Materials | Material | Pending Retopology | `design/assets/specs/player-juvenile-assets.md` |
| ASSET-007 | `sk_chr_player_juvenile` | Rig / Face | Pending Retopology | `design/assets/specs/player-juvenile-assets.md` |
| ASSET-008 | Five Player Actions | Animation | Pending Rig | `design/assets/specs/player-juvenile-assets.md` |
| ASSET-009 | `chr_player_juvenile.glb` | Runtime Package | Blocked Until Gate D | `design/assets/specs/player-juvenile-assets.md` |

## Character: Mira

| Asset ID | Name | Category | Status | Spec File |
|---|---|---|---|---|
| ASSET-010 | Mira v06 Four-View Concept | 2D Reference | Source Locked | `art/source/characters/npcs/chr_npc_mira/source_locked_v06/reference_manifest.json` |
| ASSET-011 | Mira Rodin Sculpt Baseline | 3D Source | Gate A Repair Required | `art/source/characters/npcs/chr_npc_mira/source_locked_v06/GATE_A_REVIEW.md` |
| ASSET-012 | `chr_npc_mira.glb` | Runtime Package | Static A-Pose PBR preview integrated; rig/animation pending | `art/source/characters/npcs/chr_npc_mira/modeling_locked_a_pose_v01/hunyuan_submission/reduceface_high/qa_outcome.json` |

## Character: Rowan

| Asset ID | Name | Category | Status | Spec File |
|---|---|---|---|---|
| ASSET-013 | Rowan v04 Four-View Concept | 2D Reference | Source Locked | `art/source/characters/npcs/chr_npc_rowan/source_locked_v04/reference_manifest.json` |
| ASSET-014 | Rowan Rodin Sculpt Baseline | 3D Source | Gate A Repair Required | `art/source/characters/npcs/chr_npc_rowan/source_locked_v04/GATE_A_REVIEW.md` |
| ASSET-015 | `chr_npc_rowan.glb` | Runtime Package | Blocked Until Gate D | `design/art/character-modeling-standard.md` |

## Character: Tavi

| Asset ID | Name | Category | Status | Spec File |
|---|---|---|---|---|
| ASSET-016 | Tavi v06 Four-View Concept | 2D Reference | Source Locked | `art/source/characters/npcs/chr_npc_tavi/source_locked_v06/reference_manifest.json` |

The player runtime package is present under its existing conditional Gate D
status. Mira now has a static A-Pose PBR review package in the playable scene;
it is not a rigged or animation-approved Gate D character. Rowan and Tavi still
have no runtime GLB. External NPR character kits are not on this list and must
not be added.

## Environment: Market Corner

Environment production authority: `design/art/environment-modeling-standard.md`.
Borrowed kits may enter only as structural drafts after remesh, normal transfer,
and palette remap. Japanese wood/brick identity is not a shippable look.

| Asset ID | Name | Category | Status | Spec File |
|---|---|---|---|---|
| ASSET-017 | `env_market_stall_a` | Hero Facility | Locked; Gate E pass | `art/source/environment/ASSET_LOCK_MANIFEST.json` |
| ASSET-018 | `env_ground_market_a` | Terrain | Locked; 28 m three-layer field | `art/source/environment/ASSET_LOCK_MANIFEST.json` |
| ASSET-019 | `env_hut_residential_a/b/c` | Building Module | Locked; unique crystal silhouettes | `art/source/environment/ASSET_LOCK_MANIFEST.json` |
| ASSET-020 | `fol_tree_stranger_a` | Foliage | Locked; limbs from trunk rings | `art/source/environment/ASSET_LOCK_MANIFEST.json` |
| ASSET-021 | `env_rock_facet_a/b` | Rock | Locked; faceted | `art/source/environment/ASSET_LOCK_MANIFEST.json` |
| ASSET-022 | Glow-plant clusters | Set dressing | Locked; irregular §5.6 groups | `art/source/environment/ASSET_LOCK_MANIFEST.json` |
| ASSET-023 | `env_ridge_distant_a` | Skyline | Locked; left/right valley + floor | `art/source/environment/ASSET_LOCK_MANIFEST.json` |
| ASSET-024 | `env_shelter_distant_a` | Building | Locked; crescent + amber window | `art/source/environment/ASSET_LOCK_MANIFEST.json` |
