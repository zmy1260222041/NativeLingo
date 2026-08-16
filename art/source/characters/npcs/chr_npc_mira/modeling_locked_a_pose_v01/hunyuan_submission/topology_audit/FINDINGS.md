# Topology finding — source GLB remains read-only

Input SHA-256: `e5fddc7dacef075b01e427dd9b6d4a972960b7a5bb4ee15acc455fc7e4cf8377`

| Check | Result |
| --- | ---: |
| Triangles | 499,938 |
| Vertices | 302,478 |
| Connected shells | 2,360 |
| Closed shells | 0 |
| Boundary edges | 101,816 |
| Non-manifold edges | 0 |
| Winding conflicts | 0 |
| Degenerate triangles | 0 |
| Zero-length edges | 0 |

The disconnected-shell count is not merely loose noise: 282 large structural
patches account for 77.3% of all faces and 419 medium islands account for a
further 19.7%. All patches are open. Therefore this asset is not a closed
surface mesh and must not be sent to ReduceFace unchanged.

The exact triangle-triangle self-intersection check is deferred; the universal
open-boundary condition is already a hard gate failure. See
`topology_audit.json` and `component_inventory.csv` for per-component evidence.
