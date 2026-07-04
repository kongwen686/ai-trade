# Ant Design Component Map

This project is server-rendered HTML, so Ant Design React components are represented by SSR-safe semantic classes. Keep the old domain classes for backwards compatibility, but every UI block should also carry its Ant component role.

## Component Selection

- `Layout`: use for the application shell, left navigation, top header, content workspace, and fixed market ticker.
- `Menu`: use for grouped sidebar navigation only. Do not use cards as navigation.
- `Tabs`: use when a page has multiple peer modules or dense sections, such as Backtest, Settings, and Trading. Tabs should jump to anchored sections on SSR pages.
- `PageHeader`: use for the compact page hero with title, description, and key statistics. Do not create marketing-style heroes.
- `Card`: use for bounded modules, panels, and repeated result items. Cards should contain one task or one data object.
- `Statistic`: use for KPI cards and hero summary numbers. Keep labels short and values numeric where possible.
- `Form`: use for filters, runtime settings, backtest parameters, and execution commands. Dense pages should group low-frequency options in collapsible sections.
- `Table`: use whenever users need comparison across rows, audit logs, positions, trades, settings exports, or ranked results.
- `Tag`: use for statuses, grades, reasons, warning labels, and compact metadata. Do not use tags as layout containers.
- `Button`: use for explicit commands. Primary actions are blue; destructive actions should be red and restrained.
- `Empty`: use when a module has no data. Empty states must explain the next operational action.

## Page Rules

- Signal scan: Form + segmented view switch + Cards for overview or Table for comparison.
- Terminal modules: Card grids + Tables for source data + Statistic for risk or system status.
- Backtest: Tabs + Form + Card workbench + Table export/detail sections + Empty states before data exists.
- Trading execution: Tabs + command Form + Position Table + Event Table.
- Settings: Tabs + one large Form grouped by anchors + transfer Cards for import/export.

## Migration Note

If the project moves to React later, map these classes directly:

- `.ant-layout` -> `Layout`
- `.ant-layout-sider` -> `Layout.Sider`
- `.ant-layout-header` -> `Layout.Header`
- `.ant-layout-content` -> `Layout.Content`
- `.ant-menu` / `.ant-menu-item` -> `Menu`
- `.ant-tabs` / `.ant-tabs-tab` -> `Tabs`
- `.ant-card` -> `Card`
- `.ant-statistic-card` -> `Card + Statistic`
- `.ant-form` -> `Form`
- `.ant-table-wrapper .ant-table` -> `Table`
- `.ant-tag` -> `Tag`
- `.ant-btn` -> `Button`
- `.ant-empty-state` -> `Empty`
