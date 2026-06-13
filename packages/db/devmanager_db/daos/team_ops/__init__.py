"""S4 P1 — Team Operations foundation DAOs.

包内每个 DAO 遵循 `devmanager_db.daos` 的现有模式：
- class per entity
- AsyncSession 通过 __init__ 注入
- create / get_by_id / list_* / update / delete
- update 用 clear_<field> 标志显式清空可空字段
"""
