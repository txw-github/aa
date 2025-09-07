# 参数核查器项目

## 项目概述
参数核查器是用于检查通信设备配置参数的工具，已完成重大架构升级，支持：
- 单值参数核查 (MO:PARAM:VALUE)
- 多值参数核查 (MO:PARAM:VALUES，如k1:开&k2:开&k3:关)
- 复杂条件表达式验证：(参数名1=值1 and 参数名2=值2) or (参数名3>值3 and 参数名2!=值2)
- 错配和漏配的嵌套调用
- 同时支持MO参数间的OR和AND关系
- 双sheet Excel知识库设计

## 最近修改
- 2025-09-07: **重大升级** - 实现ParameterCheckerV2，支持复杂条件表达式和嵌套校验逻辑
- 2025-09-05: 优化多值参数核查逻辑，错误信息只显示不一致的开关部分

## 新架构特性（V2版本）

### Excel知识库双sheet设计
1. **参数信息sheet**: 基础参数定义
   - MO名称、MO描述、场景类型、参数名称、参数ID、参数类型、参数含义、值描述
2. **校验规则sheet**: 复杂校验逻辑
   - 规则ID、MO名称、校验类型(错配/漏配)、参数组合、期望值、筛选条件、逻辑关系、执行顺序、后续规则、描述

### 复杂条件表达式支持
- 支持括号嵌套: `(参数名1=值1 and 参数名2=值2) or (参数名3>值3)`
- 支持比较运算符: `=`, `!=`, `>`, `<`, `>=`, `<=`
- 支持逻辑运算符: `and`, `or`
- 支持数值和字符串比较

### 核心类和方法
- `ParameterCheckerV2`: 新版本核查器主类
- `load_knowledge_base()`: 加载双sheet Excel知识库
- `evaluate_complex_condition()`: 评估复杂条件表达式
- `check_parameter_validation()`: 执行参数校验，支持嵌套逻辑
- `execute_validation_rule()`: 执行单个校验规则
- `check_misconfiguration()`: 错配检查
- `parse_multi_value_parameter()`: 解析多值参数 (k1:开&k2:关)

## 文件说明
- `parameter_checker.py`: 原版本（保留兼容性）
- `parameter_checker_v2.py`: 新版本，支持复杂条件表达式
- `参数知识库.xlsx`: 原版本知识库
- `参数知识库_v2.xlsx`: 新版本双sheet知识库

## 使用示例
```python
# 创建新版本核查器
checker = ParameterCheckerV2()

# 生成示例知识库
checker.create_sample_excel("参数知识库_v2.xlsx")

# 执行校验
errors = checker.check_parameter_validation(mo_groups, 'NRDUCELL', 'SECTOR001')
```