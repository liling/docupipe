# Changelog

## [0.1.3] - 2026-05-22

### Added
- **excel_structured Step**: 新增 Step，用 openpyxl 直接读取 Excel 文件，按 Sheet 结构化提取为 Markdown 表格
  - 支持合并单元格填充、隐藏行列跳过、空行跳过
  - 每个 Sheet 输出为独立的 `role="main"` FileItem
- **HindsightDestination 多文件支持**: 自动检测多主文件，逐一 retain 并在 document_id 后追加文件名
- **端到端测试**: 添加完整 pipeline 测试覆盖（excel_structured → convert跳过 → hindsight上传）
- **python-pptx 依赖**: 添加对 .pptx 文件转换的支持

### Changed
- Hindsight destination 不再需要 `process_roles` 配置，多主文件自动处理

### Fixed
- 修复 python-pptx 包安装问题（模块缺失）

## [0.1.2] - Earlier

- Initial release with basic pipeline support
