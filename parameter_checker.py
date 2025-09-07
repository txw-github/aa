import pandas as pd
import logging
from typing import Dict, List, Any, Optional, Set

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class ParameterChecker:
    """
    参数核查器类，用于重构现有的参数核查逻辑
    支持单值参数和多值参数（如开关组）的核查
    每行每个参数只生成一个error_param，多开关错误聚合在其中
    """

    def __init__(self, knowledge_file="参数知识库.xlsx", knowledge_sheet="空域配置"):
        """初始化参数核查器"""
        self.parameter_knowledge: Dict[str, Any] = {}
        self.missing_configs: Dict[str, List[Dict[str, str]]] = {}  # 漏配检查配置: {mo_name: [条件配置列表]}
        self.errors: List[Dict[str, Any]] = []  # 初始化错误列表
        self.load_parameter_knowledge(knowledge_file, knowledge_sheet)

    def load_parameter_knowledge(self, file_path="参数知识库.xlsx", main_sheet="空域配置",
                                 missing_sheet=None) -> bool:
        """从Excel文件中加载参数知识库，优化数值类型处理"""
        try:
            # 读取Excel文件时，将可能为整数的列指定为字符串先读取，避免自动转为浮点数
            # 读取主配置sheet
            main_df = pd.read_excel(
                file_path,
                sheet_name=main_sheet,
                dtype=str
            )

            # 处理漏配检查配置sheet（可选）
            self.missing_configs = {}
            if missing_sheet:
                try:
                    missing_df = pd.read_excel(
                        file_path,
                        sheet_name=missing_sheet,
                        dtype=str
                    )

                    # 验证漏配sheet必要列
                    missing_required = ['MO名称', '检查字段', '检查值', '逻辑关系']
                    missing_missing = [col for col in missing_required if col not in missing_df.columns]
                    if missing_missing:
                        logger.warning(f"漏配sheet缺少必要列: {missing_missing}")
                    else:
                        # 处理漏配检查配置
                        for _, row in missing_df.iterrows():
                            mo_name = row['MO名称'].strip()
                            if mo_name not in self.missing_configs:
                                self.missing_configs[mo_name] = []
                            self.missing_configs[mo_name].append({
                                'field': row['检查字段'].strip(),
                                'value': row['检查值'].strip(),
                                'logic': row['逻辑关系'].strip().upper() if row.get('逻辑关系') else 'AND'
                            })
                except Exception as e:
                    logger.warning(f"未能加载漏配配置sheet '{missing_sheet}': {str(e)}")

            # 验证基础必要的列是否存在
            base_required_columns = ['MO名称', '参数名称', '参数ID', '期望值', '参数描述', '条件表达式', '参数类型']
            missing_base_columns = [col for col in base_required_columns if col not in main_df.columns]

            if missing_base_columns:
                logger.error(f"Excel文件缺少必要的基础列: {missing_base_columns}")
                return False

            # 清空现有的参数知识库
            self.parameter_knowledge = {}

            # 按MO名称和参数名称双层分组
            for (mo_name, param_name), param_group in main_df.groupby(['MO名称', '参数名称']):
                # 获取参数类型
                # 确保参数类型转换为字符串后再处理
                param_type = str(param_group.iloc[0]['参数类型']).strip()
                if param_type not in ['single', 'multiple']:
                    logger.warning(f"参数 {mo_name}.{param_name} 有无效的参数类型: {param_type}，将被视为单值参数")
                    param_type = 'single'

                # 对于多值参数，检查是否有"值描述"列
                if param_type == 'multiple' and '值描述' not in main_df.columns:
                    logger.error(f"多值参数 {mo_name}.{param_name} 缺少必要的'值描述'列")
                    continue

                # 初始化MO级别信息
                if mo_name not in self.parameter_knowledge:
                    self.parameter_knowledge[mo_name] = {
                        "mo_name": mo_name,
                        "mo_description": param_group.iloc[0].get('MO描述', ''),
                        "scenario": param_group.iloc[0].get('场景类型', ''),
                        "parameters": {}
                    }

                # 初始化参数信息
                param_info = {
                    "parameter_id": param_group.iloc[0].get('参数ID', ''),
                    "parameter_name": param_name,
                    "parameter_type": param_type,
                    "parameter_description": param_group.iloc[0].get('参数描述', ''),
                    "check_items": [],  # 存储所有检查项（单值或开关）及对应条件
                    "switch_descriptions": {}  # 多值参数专用：{开关名称: 开关描述}
                }

                # 处理每个检查项（每行对应一个检查项）
                for _, row in param_group.iterrows():
                    # 处理期望值，尝试转换为正确的类型（整数/字符串）
                    raw_expected_value = str(row.get('期望值', '')).strip()
                    processed_expected = self._convert_to_proper_type(raw_expected_value)

                    # 确保条件表达式转换为字符串后再处理
                    condition = row.get('条件表达式', '')
                    str_condition = str(condition).strip() if pd.notna(condition) else ''

                    check_item = {
                        "condition": str_condition,
                    }

                    # 处理多值参数（开关）
                    if param_type == 'multiple' and ':' in raw_expected_value:
                        switch_name, expected_state = raw_expected_value.split(':', 1)
                        switch_name = switch_name.strip()
                        expected_state = expected_state.strip()

                        # 转换开关状态的类型
                        processed_state = self._convert_to_proper_type(expected_state)

                        check_item["switch_name"] = switch_name
                        check_item["expected_state"] = processed_state
                        # 多值参数使用"值描述"列作为开关描述
                        check_item["value_description"] = row.get('值描述', '')
                        param_info["switch_descriptions"][switch_name] = check_item["value_description"]

                    # 处理单值参数
                    else:
                        check_item["expected_value"] = processed_expected

                    param_info["check_items"].append(check_item)

                # 初始化MO配置
                # 确保MO配置始终存在，避免未定义错误
                mo_config = self.parameter_knowledge.setdefault(mo_name, {})
                mo_config.setdefault("mo_name", mo_name)
                mo_config.setdefault("parameters", {})

                # 保留原漏配检查配置作为兼容处理
                mo_config.setdefault("missing_config", {})
                filter_field = str(row.get("漏配检查字段", param_name)).strip()
                filter_value = str(row.get("漏配检查值", "")).strip()
                mo_config["missing_config"]["filter_field"] = filter_field
                mo_config["missing_config"]["filter_value"] = filter_value

                # 加载参数验证配置
                # 确保验证参数列表是字符串类型
                validation_params = str(row.get("验证参数列表", "")).strip()
                if validation_params:
                    mo_config.setdefault("validation_params", [])
                    # 支持分号分隔多个参数配置，增强容错处理
                    for param_str in validation_params.split("; "):
                        param_str = param_str.strip()
                        if param_str and ":" in param_str:
                            parts = param_str.split(":")
                            if len(parts) == 3:
                                p_mo, p_name, p_value = parts
                                mo_config["validation_params"].append((p_mo.strip(), p_name.strip(), p_value.strip()))
                            else:
                                logger.warning(f"参数验证配置格式错误: {param_str}，应为'MO名称:参数名称:期望值'")

                # 将参数信息加入知识库
                self.parameter_knowledge[mo_name]["parameters"][param_name] = param_info

            logger.info(f"成功从 {file_path} 的 '{sheet_name}' Sheet 加载了参数知识库")
            logger.info(f"包含 {len(self.parameter_knowledge)} 个MO类型")

            return True

        except FileNotFoundError:
            logger.error(f"文件 {file_path} 不存在")
            return False
        except Exception as e:
            logger.error(f"加载参数知识库时发生错误: {str(e)}")
            return False

    def _convert_to_proper_type(self, value: Any) -> str:
        """将值转换为合适的字符串类型表示"""
        if value is None:
            return ""
        # 确保输入值为字符串类型
        str_value = str(value).strip()
        if not str_value:
            return ""
        # 尝试转换为整数
        try:
            return str(int(str_value))
        except ValueError:
            pass
        # 尝试转换为浮点数
        try:
            float_val = float(str_value)
            if float_val.is_integer():
                return str(int(float_val))
            return str(float_val)
        except ValueError:
            pass
        # 尝试转换为布尔值
        if str_value.lower() == 'true':
            return 'true'
        elif str_value.lower() == 'false':
            return 'false'
        # 都失败则返回处理后的字符串
        return str_value

    def check_configurable_mo(self, groups: Dict[str, pd.DataFrame], mo_name: str, sector_id: str) -> List[
        Dict[str, Any]]:
        """通用MO检查方法: 检查漏配和参数验证并记录错误

        Args:
            groups: 数据组字典
            mo_name: MO名称
            sector_id: 扇区ID
            filter_field: 漏配检查字段名
            filter_value: 漏配检查目标值
            expected_params: 参数验证列表，格式为[(参数名, 期望值), ...]

        Returns:
            错误信息列表
        """
        errors = []
        # 从知识库获取配置
        if mo_name not in self.parameter_knowledge:
            errors.append({
                'sector_id': sector_id,
                'mo_name': mo_name,
                'error_type': '知识库配置不存在',
                'message': f'{mo_name}未在参数知识库中配置',
                'current_value': None,
                'expected_value': None
            })
            return errors

    def _check_multi_condition_missing(self, mo_name: str, mo_data: pd.DataFrame, sector_id: str,
                                       errors: List[Dict[str, Any]]) -> bool:
        """基于多条件组合检查MO是否存在漏配参数"""
        conditions = self.missing_configs.get(mo_name, [])
        if not conditions:
            # 使用传统漏配检查作为降级方案
            mo_config = self.parameter_knowledge.get(mo_name, {})
            missing_config = mo_config.get("missing_config", {})
            filter_field = missing_config.get("filter_field")
            filter_value = missing_config.get("filter_value")
            if filter_field and filter_value:
                valid_records = mo_data[mo_data[filter_field] == filter_value]
                if len(valid_records) == 0:
                    self.errors.append({
                        'sector_id': sector_id,
                        'mo_name': mo_name,
                        'param_name': filter_field,
                        'error_type': '漏配',
                        'message': f'不存在{filter_field}值为"{filter_value}"的记录',
                        'current_value': None,
                        'expected_value': filter_value
                    })
                    return False
            return True

        # 评估所有条件
        condition_results = []
        for cond in conditions:
            field = cond['field']
            expected_value = cond['value']
            if field not in mo_data.columns:
                self.errors.append({
                    'sector_id': sector_id,
                    'mo_name': mo_name,
                    'param_name': field,
                    'error_type': '列不存在',
                    'message': f'{mo_name}中不存在{field}列',
                    'current_value': None,
                    'expected_value': expected_value
                })
                return False

            # 转换值为合适类型并比较
            actual_value = self._convert_to_proper_type(mo_data[field].iloc[0])
            expected_value = self._convert_to_proper_type(expected_value)
            condition_results.append(actual_value == expected_value)

        # 应用逻辑关系
        logic = conditions[0]['logic']
        if logic == 'AND':
            all_met = all(condition_results)
            if not all_met:
                failed = [f"{cond['field']}={cond['value']}" for i, cond in enumerate(conditions) if
                          not condition_results[i]]
                self.errors.append({
                    'sector_id': sector_id,
                    'mo_name': mo_name,
                    'error_type': '漏配',
                    'message': f'未满足所有条件: {failed} (逻辑关系: {logic})',
                    'current_value': None,
                    'expected_value': '; '.join([cond['value'] for cond in conditions])
                })
                return False
        elif logic == 'OR':
            any_met = any(condition_results)
            if not any_met:
                failed = [f"{cond['field']}={cond['value']}" for cond in conditions]
                self.errors.append({
                    'sector_id': sector_id,
                    'mo_name': mo_name,
                    'error_type': '漏配',
                    'message': f'未满足任何条件: {failed} (逻辑关系: {logic})',
                    'current_value': None,
                    'expected_value': '; '.join([cond['value'] for cond in conditions])
                })
                return False
        else:
            self.errors.append({
                'sector_id': sector_id,
                'mo_name': mo_name,
                'error_type': '配置错误',
                'message': f'未知逻辑关系: {logic}',
                'current_value': None,
                'expected_value': 'AND/OR'
            })
            return False

        return True

        mo_config = self.parameter_knowledge[mo_name]
        missing_config = mo_config.get("missing_config", {})
        filter_field = missing_config.get("filter_field", "")
        filter_value = missing_config.get("filter_value", "")
        expected_params = mo_config.get("validation_params", [])

        # 验证漏配检查配置
        if not filter_field or not filter_value:
            errors.append({
                'sector_id': sector_id,
                'mo_name': mo_name,
                'error_type': '配置不完整',
                'message': f'{mo_name}漏配检查配置不完整',
                'current_value': None,
                'expected_value': None
            })
            return errors

        if mo_name not in groups:
            errors.append({
                'sector_id': sector_id,
                'mo_name': mo_name,
                'error_type': '数据不存在',
                'message': f'{mo_name}数据不存在',
                'current_value': None,
                'expected_value': None
            })
            return errors

        mo_data = groups[mo_name]
        if filter_field not in mo_data.columns:
            errors.append({
                'sector_id': sector_id,
                'mo_name': mo_name,
                'param_name': filter_field,
                'error_type': '列不存在',
                'message': f'{mo_name}中不存在{filter_field}列',
                'current_value': None,
                'expected_value': None
            })
            return errors

        # 使用多条件漏配检查
        if not self._check_multi_condition_missing(mo_name, mo_data, sector_id, errors):
            return errors

        # 参数验证（漏配检查通过后才执行）
        if not errors:  # 只有漏配检查无错误时才进行参数验证
            for param_name, expected_value in expected_params:
                if param_name not in mo_data.columns:
                    errors.append({
                        'sector_id': sector_id,
                        'mo_name': mo_name,
                        'param_name': param_name,
                        'error_type': '列不存在',
                        'message': f'{mo_name}中不存在{param_name}列',
                        'current_value': None,
                        'expected_value': expected_value
                    })
                    continue

            actual_value = valid_records.iloc[0][param_name]
            if str(actual_value) != expected_value:
                errors.append({
                    'sector_id': sector_id,
                    'mo_name': mo_name,
                    'param_name': param_name,
                    'error_type': '参数错误',
                    'message': f'参数值不匹配: 实际值={actual_value}, 期望值={expected_value}',
                    'current_value': actual_value,
                    'expected_value': expected_value
                })

        return errors

    def check_nrcellfreqrelation(self, groups: Dict[str, pd.DataFrame], mo_name: str, sector_id: str) -> List[
        Dict[str, Any]]:
        """NRCELLFREQRELATION专用检查方法，调用通用检查方法"""
        return self.check_configurable_mo(groups, mo_name, sector_id)

    def check_single_param(self, groups: Dict[str, pd.DataFrame], mo_name: str,
                           param_name: str, sector_id: str) -> pd.DataFrame:
        """检查单个参数是否符合预期值并记录结果"""
        # 输入参数验证
        if not groups or mo_name not in groups:
            logger.warning(f"SectorId {sector_id}: {mo_name} 数据不存在")
            return pd.DataFrame()

        tmp = groups[mo_name].copy()
        if tmp.empty:
            logger.warning(f"SectorId {sector_id}: {mo_name} 数据为空")
            return pd.DataFrame()

        if param_name not in tmp.columns:
            logger.warning(f"SectorId {sector_id}: {mo_name} 缺少参数列: {param_name}")
            return pd.DataFrame()

        # 获取参数知识库配置
        mo_config = self.parameter_knowledge.get(mo_name)
        if not mo_config:
            logger.warning(f"SectorId {sector_id}: 参数知识库中未找到 {mo_name} 的配置")
            return pd.DataFrame()

        param_info = mo_config.get("parameters", {}).get(param_name)
        if not param_info:
            logger.warning(f"SectorId {sector_id}: 参数知识库中未找到 {mo_name}.{param_name} 的配置")
            return pd.DataFrame()

        # 参数检查与错误收集
        valid_mask = pd.Series(True, index=tmp.index)  # 初始化为全部有效
        error_details = []  # 每个元素是一个字典，对应一行的错误信息
        mod_commands = []

        # 处理当前值，转换为合适的类型
        current_values = tmp[param_name].apply(lambda x: self._convert_to_proper_type(str(x).strip()))

        # 根据参数类型分派处理
        if param_info["parameter_type"] == 'multiple':
            self._process_multi_value_param(tmp, param_info, current_values, valid_mask,
                                            error_details, mod_commands, mo_name, sector_id)
        else:
            self._process_single_value_param(tmp, param_info, current_values, valid_mask,
                                             error_details, mod_commands, mo_name, sector_id)

        # 生成结果
        result = tmp.copy()
        result['valid'] = valid_mask
        result['mod_command'] = mod_commands
        result['error_details'] = error_details
        result['sector_id'] = sector_id
        result['mo_name'] = mo_name
        result['parameter_name'] = param_name

        # 只返回无效的行
        invalid_rows = result[~valid_mask].copy()

        if len(invalid_rows) > 0:
            logger.info(f"SectorId {sector_id}: {mo_name}.{param_name} 发现 {len(invalid_rows)} 条配置错误")
        else:
            logger.info(f"SectorId {sector_id}: {mo_name}.{param_name} 所有参数配置正确")

        return invalid_rows

    def _evaluate_condition(self, condition: str, current_params: Dict[str, Any]) -> bool:
        """评估条件表达式是否成立"""
        if not condition:
            return True

        try:
            # 支持多条件用逗号分隔（逻辑与关系）
            conditions = [cond.strip() for cond in condition.split(',') if cond.strip()]
            if not conditions:
                return True

            # 所有条件都必须满足
            for cond in conditions:
                if '=' in cond:
                    param_name, expected_value = cond.split('=', 1)
                    param_name = param_name.strip()
                    expected_value = self._convert_to_proper_type(expected_value.strip())
                    current_value = current_params.get(param_name, '')
                    # 转换当前值为合适的类型进行比较
                    current_value = self._convert_to_proper_type(str(current_value).strip())

                    if current_value != expected_value:
                        return False
                else:
                    return False  # 不包含=的条件视为无效条件

            return True
        except Exception as e:
            logger.error(f"评估条件表达式错误: {condition}, 错误: {str(e)}")
            return False

    def _process_multi_value_param(self, tmp: pd.DataFrame, param_info: Dict[str, Any],
                                   current_values: pd.Series, valid_mask: pd.Series,
                                   error_details: List[Dict[str, Any]], mod_commands: List[str],
                                   mo_name: str, sector_id: str) -> None:
        """处理多值参数（如开关组）的检查逻辑"""
        for idx, current_value in current_values.items():
            current_row = tmp.iloc[idx].to_dict()
            # 转换当前行所有参数为合适的类型
            converted_row = {k: self._convert_to_proper_type(str(v).strip()) for k, v in current_row.items()}
            switches = self._parse_multi_value(str(current_value))

            # 转换开关值为合适的类型
            converted_switches = {k: self._convert_to_proper_type(v) for k, v in switches.items()}

            # 收集所有适用的检查项和对应的错误
            applicable_checks = []
            switch_errors = []
            mod_params = []

            # 检查每个检查项（每个开关对应一个检查项）
            for check_item in param_info["check_items"]:
                # 评估当前检查项的条件
                if self._evaluate_condition(check_item["condition"], converted_row):
                    applicable_checks.append(check_item)
                    switch_name = check_item["switch_name"]
                    expected_state = check_item["expected_state"]
                    current_switch_value = converted_switches.get(switch_name, '')

                    # 检查开关状态是否匹配
                    if current_switch_value != expected_state:
                        switch_errors.append({
                            'switch_name': switch_name,
                            'expected_state': expected_state,
                            'current_state': current_switch_value,
                            'value_description': check_item["value_description"],
                            'description': param_info["parameter_description"]
                        })
                        mod_params.append(f"{switch_name}={expected_state}")

            # 确定是否有错误
            if switch_errors:
                valid_mask[idx] = False

                # 构建单个error_param，包含所有开关错误
                error_details.append({
                    'parameter_name': param_info['parameter_name'],
                    'parameter_id': param_info['parameter_id'],
                    'parameter_description': param_info['parameter_description'],
                    'switch_errors': switch_errors,
                    'expected_values': {err['switch_name']: err['expected_state'] for err in switch_errors},
                    'current_values': {err['switch_name']: err['current_state'] for err in switch_errors},
                })

                # 构建MOD命令
                mod_commands.append(
                    f"MOD {mo_name}:{param_info['parameter_id']}={';'.join(mod_params)};"
                )
            else:
                error_details.append({})
                mod_commands.append('')

    def _process_single_value_param(self, tmp: pd.DataFrame, param_info: Dict[str, Any],
                                    current_values: pd.Series, valid_mask: pd.Series,
                                    error_details: List[Dict[str, Any]], mod_commands: List[str],
                                    mo_name: str, sector_id: str) -> None:
        """处理单值参数的检查逻辑"""
        for idx, row in tmp.iterrows():
            current_row = row.to_dict()
            # 转换当前行所有参数为合适的类型
            converted_row = {k: self._convert_to_proper_type(str(v).strip()) for k, v in current_row.items()}
            current_value = current_values[idx]

            # 检查每个检查项
            error_found = False
            expected_value = None
            applicable_conditions = []

            for check_item in param_info["check_items"]:
                # 评估条件
                if self._evaluate_condition(check_item["condition"], converted_row):
                    applicable_conditions.append(check_item["condition"])
                    expected_value = check_item["expected_value"]

                    # 检查值是否匹配
                    if current_value != expected_value:
                        error_found = True
                        break

            if error_found and expected_value is not None:
                valid_mask[idx] = False
                # 单个error_param
                error_details.append({
                    "parameter_name": param_info["parameter_name"],
                    "parameter_id": param_info["parameter_id"],
                    "parameter_description": param_info["parameter_description"],
                    "expected_value": expected_value,
                    "current_value": current_value,
                    "conditions": applicable_conditions
                })
                mod_commands.append(f"MOD {mo_name}:{param_info['parameter_id']}={expected_value};")
            else:
                error_details.append({})
                mod_commands.append('')

    def _parse_multi_value(self, value_str: str) -> Dict[str, str]:
        """解析多值参数（如开关组）"""
        result = {}
        if not isinstance(value_str, str):
            return result

        # 处理可能的不同分隔符
        separators = ['&', ',', ';']
        for sep in separators:
            if sep in value_str:
                parts = value_str.split(sep)
                break
        else:
            parts = [value_str]

        for part in parts:
            if ':' in part:
                key, val = part.split(':', 1)
                result[key.strip()] = val.strip()

        return result

    def check_multiple_params(self, groups: Dict[str, pd.DataFrame], mo_name: str,
                              param_names: List[str], sector_id: str) -> pd.DataFrame:
        """检查多个参数是否符合预期值并记录结果"""
        all_errors = pd.DataFrame()

        for param_name in param_names:
            errors = self.check_single_param(groups, mo_name, param_name, sector_id)
            all_errors = pd.concat([all_errors, errors], ignore_index=True)

        return all_errors

    def create_sample_excel(self, file_path: str = '参数知识库.xlsx') -> None:
        """创建示例参数知识库Excel文件，包含完整配置规则说明"""
        # 创建示例数据，展示三种配置场景
        data = [
            # 配置规则说明行
            {
                'MO名称': '=== 配置规则说明 ===',
                'MO描述': '必填项: MO名称/参数名称/参数ID/参数类型',
                '场景类型': '参数类型: single(单值)/multiple(多开关)',
                '参数名称': '期望值与漏配检查值互斥，二选一填写',
                '参数ID': '验证参数列表格式: MO名称:参数名称:期望值;多个用;分隔',
                '参数类型': '',
                '参数含义': '配置规则说明(重点)',
                '期望值': '有值时触发参数值稽核(与漏配检查值二选一)',

                '漏配检查值': '有值时触发漏配检查(与期望值二选一)',
                '条件表达式': '格式:参数名=值,多条件用逗号分隔',
                '值描述': '多值参数开关状态说明',
                '验证参数列表': '格式:MO名称:参数名称:期望值;多个用;分隔\n⚠️关键逻辑:漏配检查通过后自动触发以下验证:\n1. MO名称:定位目标网元数据\n2. 参数名称:定位具体参数\n3. 期望值:验证实际值是否匹配\n示例:NRCELLFREQRELATION:连接态频率优先级:5'
            },
            # 场景1: 仅参数稽核(只有期望值)
            {
                'MO名称': 'NRDUCELL',
                'MO描述': 'NR DU小区',
                '场景类型': '空域配置',
                '参数名称': '小区半径(米)',
                '参数ID': 'CellRadius',
                '参数类型': 'single',
                '参数含义': '小区覆盖半径',
                '期望值': '300',  # 有期望值时进行参数稽核

                '漏配检查值': '',  # 漏配检查值为空
                '条件表达式': '',
                '值描述': '',
                '验证参数列表': ''  # 无需验证其他参数
            },
            # 场景2: 仅漏配检查(只有漏配检查值)
            {
                'MO名称': 'NRCELL',
                'MO描述': 'NR小区',
                '场景类型': '空域配置',
                '参数名称': '跟踪区码',
                '参数ID': 'TrackingAreaCode',
                '参数类型': 'single',
                '参数含义': '小区所属跟踪区',
                '期望值': '',  # 期望值为空

                '漏配检查值': '100',  # 有漏配检查值时进行漏配检查
                '条件表达式': '',
                '值描述': '',
                '验证参数列表': ''
            },
            # 场景3: 漏配检查+参数验证组合
            {
                'MO名称': 'NRCELLFREQRELATION',
                'MO描述': 'NR小区频率关系',
                '场景类型': '空域配置',
                '参数名称': 'SSB频域位置',
                '参数ID': '3001',
                '参数类型': 'single',
                '参数含义': 'SSB的频域位置',
                '期望值': '',  # 期望值为空

                '漏配检查值': '7783',  # 有漏配检查值时进行漏配检查
                '条件表达式': '',
                '值描述': '',
                # 验证参数列表格式: MO名称:参数名称:期望值;多个用;分隔
                '验证参数列表': 'NRCELLFREQRELATION:连接态频率优先级:5;NRCELLFREQRELATION:测量频点:38400'
            },
            # 场景4: 多MO参数关联验证
            {
                'MO名称': 'NRCELL',
                'MO描述': 'NR小区',
                '场景类型': '空域配置',
                '参数名称': '工作带宽',
                '参数ID': 'OperatingBandwidth',
                '参数类型': 'single',
                '参数含义': '小区工作带宽',
                '期望值': '',  # 期望值为空

                '漏配检查值': '100',  # 先检查漏配
                '条件表达式': '',
                '值描述': '',
                # 验证参数列表引用其他MO的参数
                '验证参数列表': 'NRDUCELL:最大传输功率:43;NRCELLPDSCH:调制方式:64QAM'
            }
        ]

        # 创建DataFrame并保存为Excel
        df = pd.DataFrame(data)
        # 创建漏配检查sheet数据
        missing_data = [
            {
                'MO名称': '=== 漏配检查规则说明 ===',
                '检查字段': '必填项: MO名称/检查字段/检查值/逻辑关系',
                '检查值': '逻辑关系: AND(所有条件满足)/OR(任一条件满足)',
                '逻辑关系': '多条件时所有行的逻辑关系必须一致',
            },
            # 场景1: AND逻辑（所有条件必须满足）
            {
                'MO名称': 'NRCELLFREQRELATION',
                '检查字段': 'SSB频域位置',
                '检查值': '7783',
                '逻辑关系': 'AND',
            },
            {
                'MO名称': 'NRCELLFREQRELATION',
                '检查字段': '连接态频率优先级',
                '检查值': '5',
                '逻辑关系': 'AND',
            },
            # 场景2: OR逻辑（任一条件满足）
            {
                'MO名称': 'NRCELL',
                '检查字段': '工作带宽',
                '检查值': '100',
                '逻辑关系': 'OR',
            },
            {
                'MO名称': 'NRCELL',
                '检查字段': '工作带宽',
                '检查值': '200',
                '逻辑关系': 'OR',
            }
        ]
        missing_df = pd.DataFrame(missing_data)

        with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='空域配置', index=False)
            missing_df.to_excel(writer, sheet_name='漏配', index=False)
        logger.info(f"示例参数知识库已生成: {file_path}")
        logger.info(
            "使用说明: 1. 运行此方法生成示例Excel; 2. 根据实际需求修改参数值; 3. 确保期望值和漏配检查值只有一个有值")


# 核心辅助函数 - 获取共同小区组
def _get_common_groups(mo_data):
    """获取所有MO数据共有的小区ID组"""

    def get_group_keys(df):
        return set(df.groupby(['f_site_id', 'f_cell_id']).groups.keys())

    all_groups = [get_group_keys(df) for df in mo_data.values()]
    return set.intersection(*all_groups) if all_groups else set()


if __name__ == "__main__":
    # 创建测试环境
    checker = ParameterChecker()

    # 创建示例Excel文件
    # checker.create_sample_excel()

    # 重新加载参数知识库
    checker.load_parameter_knowledge()

    # 创建测试数据
    datas = {
        "result": {
            "NRDUCELL": [
                {
                    "f_site_id": "13566583",
                    "f_cell_id": "4",
                    "Name": "YC5GHTA东台_城南OLT5G宏站BBU4_[13566583][130.1][场景]",
                    "f_local_cell_id": "4",
                    "NR DU小区标识": "4",
                    "小区半径(米)": "4000"
                }
            ],
            "NRCELLALGOSWITCH": [
                {
                    "f_site_id": "13566583",
                    "f_cell_id": "4",
                    "Name": "YC5GHTA东台_城南OLT5G宏站BBU4_[13566583][130.1][场景]",
                    "f_local_cell_id": "4",
                    "NR小区标识": "4",
                    "异频切换算法开关": "基于覆盖的异频切换开关:开&基于频率优先级的异频切换开关:关&异频重定向开关:开&基于运营商专用优先级的异频切换开关:关&音视频异频切换配合开关:开&基于业务的异频切换开关:关&基于覆盖的异频盲切换开关:关&FR1到FR2频点轮询选择开关:关&基于上行干扰的异频切换开关:关&基于SSB SINR的异频切换开关:关&NSA基于上行干扰的异频切换开关:关&异频切换配合开关:关&基于能效的异频切换开关:关&基于MBS兴趣指示的异频切换开关:关&基于业务的异频盲切换开关:关"
                }
            ],
            "NRCELLFREQRELATION": [
                {
                    "f_site_id": "13566583",
                    "f_cell_id": "4",
                    "Name": "YC5GHTA东台_城南OLT5G宏站BBU4_[13566583][130.1][场景]",
                    "f_local_cell_id": "4",
                    "NR小区标识": "4",
                    "SSB频域位置": "2202",
                    "连接态频率优先级": "1",
                    "小区重选优先级": "4",
                    "最低接收电平(2dBm)": "-64",
                    "低优先级重选门限(2dB)": "19"
                },
                {
                    "f_site_id": "13566583",
                    "f_cell_id": "4",
                    "Name": "YC5GHTA东台_城南OLT5G宏站BBU4_[13566583][130.1][场景]",
                    "f_local_cell_id": "4",
                    "NR小区标识": "4",
                    "SSB频域位置": "5361",
                    "连接态频率优先级": "1",
                    "小区重选优先级": "5",
                    "最低接收电平(2dBm)": "-64",
                    "低优先级重选门限(2dB)": "10"
                },
                {
                    "f_site_id": "13566583",
                    "f_cell_id": "4",
                    "Name": "YC5GHTA东台_城南OLT5G宏站BBU4_[13566583][130.1][场景]",
                    "f_local_cell_id": "4",
                    "NR小区标识": "4",
                    "SSB频域位置": "7714",
                    "连接态频率优先级": "2",
                    "小区重选优先级": "6",
                    "最低接收电平(2dBm)": "-64",
                    "低优先级重选门限(2dB)": "10"
                },
                {
                    "f_site_id": "13566583",
                    "f_cell_id": "4",
                    "Name": "YC5GHTA东台_城南OLT5G宏站BBU4_[13566583][130.1][场景]",
                    "f_local_cell_id": "4",
                    "NR小区标识": "4",
                    "SSB频域位置": "7853",
                    "连接态频率优先级": "2",
                    "小区重选优先级": "6",
                    "最低接收电平(2dBm)": "-64",
                    "低优先级重选门限(2dB)": "10"
                }
            ],
            "NRCELLINTERFHOMEAGRP": [
                {
                    "f_site_id": "13566583",
                    "f_cell_id": "4",
                    "Name": "YC5GHTA东台_城南OLT5G宏站BBU4_[13566583][130.1][场景]",
                    "f_local_cell_id": "4",
                    "NR小区标识": "4",
                    "异频切换测量参数组标识": "0",
                    "基于覆盖的异频A5 RSRP触发门限1(dBm)": "-105",
                    "基于覆盖的异频A5 RSRP触发门限2(dBm)": "-100",
                    "基于覆盖的异频A2 RSRP触发门限(dBm)": "-105",
                    "基于覆盖的异频A1 RSRP触发门限(dBm)": "-100",
                    "异频测量事件时间迟滞(毫秒)": "320",
                    "异频测量事件幅度迟滞(0.5dB)": "2",
                    "异频A1A2时间迟滞(毫秒)": "320",
                    "异频A1A2幅度迟滞(0.5dB)": "2"
                }
            ],
            "NRCELLQCIBEARER": [
                {
                    "f_site_id": "13566583",
                    "f_cell_id": "4",
                    "Name": "YC5GHTA东台_城南OLT5G宏站BBU4_[13566583][130.1][场景]",
                    "f_local_cell_id": "4",
                    "NR小区标识": "4",
                    "服务质量等级": "1",
                    "异频切换测量参数组标识": "0"
                },
                {
                    "f_site_id": "13566583",
                    "f_cell_id": "4",
                    "Name": "YC5GHTA东台_城南OLT5G宏站BBU4_[13566583][130.1][场景]",
                    "f_local_cell_id": "4",
                    "NR小区标识": "4",
                    "服务质量等级": "2",
                    "异频切换测量参数组标识": "0"
                },
                {
                    "f_site_id": "13566583",
                    "f_cell_id": "4",
                    "Name": "YC5GHTA东台_城南OLT5G宏站BBU4_[13566583][130.1][场景]",
                    "f_local_cell_id": "4",
                    "NR小区标识": "4",
                    "服务质量等级": "3",
                    "异频切换测量参数组标识": "0"
                },
                {
                    "f_site_id": "13566583",
                    "f_cell_id": "4",
                    "Name": "YC5GHTA东台_城南OLT5G宏站BBU4_[13566583][130.1][场景]",
                    "f_local_cell_id": "4",
                    "NR小区标识": "4",
                    "服务质量等级": "4",
                    "异频切换测量参数组标识": "0"
                },
                {
                    "f_site_id": "13566583",
                    "f_cell_id": "4",
                    "Name": "YC5GHTA东台_城南OLT5G宏站BBU4_[13566583][130.1][场景]",
                    "f_local_cell_id": "4",
                    "NR小区标识": "4",
                    "服务质量等级": "5",
                    "异频切换测量参数组标识": "0"
                },
                {
                    "f_site_id": "13566583",
                    "f_cell_id": "4",
                    "Name": "YC5GHTA东台_城南OLT5G宏站BBU4_[13566583][130.1][场景]",
                    "f_local_cell_id": "4",
                    "NR小区标识": "4",
                    "服务质量等级": "6",
                    "异频切换测量参数组标识": "0"
                },
                {
                    "f_site_id": "13566583",
                    "f_cell_id": "4",
                    "Name": "YC5GHTA东台_城南OLT5G宏站BBU4_[13566583][130.1][场景]",
                    "f_local_cell_id": "4",
                    "NR小区标识": "4",
                    "服务质量等级": "7",
                    "异频切换测量参数组标识": "0"
                },
                {
                    "f_site_id": "13566583",
                    "f_cell_id": "4",
                    "Name": "YC5GHTA东台_城南OLT5G宏站BBU4_[13566583][130.1][场景]",
                    "f_local_cell_id": "4",
                    "NR小区标识": "4",
                    "服务质量等级": "8",
                    "异频切换测量参数组标识": "0"
                },
                {
                    "f_site_id": "13566583",
                    "f_cell_id": "4",
                    "Name": "YC5GHTA东台_城南OLT5G宏站BBU4_[13566583][130.1][场景]",
                    "f_local_cell_id": "4",
                    "NR小区标识": "4",
                    "服务质量等级": "9",
                    "异频切换测量参数组标识": "0"
                },
                {
                    "f_site_id": "13566583",
                    "f_cell_id": "4",
                    "Name": "YC5GHTA东台_城南OLT5G宏站BBU4_[13566583][130.1][场景]",
                    "f_local_cell_id": "4",
                    "NR小区标识": "4",
                    "服务质量等级": "65",
                    "异频切换测量参数组标识": "0"
                },
                {
                    "f_site_id": "13566583",
                    "f_cell_id": "4",
                    "Name": "YC5GHTA东台_城南OLT5G宏站BBU4_[13566583][130.1][场景]",
                    "f_local_cell_id": "4",
                    "NR小区标识": "4",
                    "服务质量等级": "66",
                    "异频切换测量参数组标识": "0"
                },
                {
                    "f_site_id": "13566583",
                    "f_cell_id": "4",
                    "Name": "YC5GHTA东台_城南OLT5G宏站BBU4_[13566583][130.1][场景]",
                    "f_local_cell_id": "4",
                    "NR小区标识": "4",
                    "服务质量等级": "69",
                    "异频切换测量参数组标识": "0"
                },
                {
                    "f_site_id": "13566583",
                    "f_cell_id": "4",
                    "Name": "YC5GHTA东台_城南OLT5G宏站BBU4_[13566583][130.1][场景]",
                    "f_local_cell_id": "4",
                    "NR小区标识": "4",
                    "服务质量等级": "70",
                    "异频切换测量参数组标识": "0"
                },
                {
                    "f_site_id": "13566583",
                    "f_cell_id": "4",
                    "Name": "YC5GHTA东台_城南OLT5G宏站BBU4_[13566583][130.1][场景]",
                    "f_local_cell_id": "4",
                    "NR小区标识": "4",
                    "服务质量等级": "75",
                    "异频切换测量参数组标识": "0"
                },
                {
                    "f_site_id": "13566583",
                    "f_cell_id": "4",
                    "Name": "YC5GHTA东台_城南OLT5G宏站BBU4_[13566583][130.1][场景]",
                    "f_local_cell_id": "4",
                    "NR小区标识": "4",
                    "服务质量等级": "79",
                    "异频切换测量参数组标识": "0"
                }
            ],
            "NRCELLRESELCONFIG": [
                {
                    "f_site_id": "13566583",
                    "f_cell_id": "4",
                    "Name": "YC5GHTA东台_城南OLT5G宏站BBU4_[13566583][130.1][场景]",
                    "f_local_cell_id": "4",
                    "NR小区标识": "4",
                    "非同频测量RSRP触发门限(2dB)": "10",
                    "服务频点低优先级RSRP重选门限(2dB)": "9"
                }
            ]
        }
    }
    mo_datas = datas['result']
    mo_datas = {key: pd.DataFrame(df) for key, df in mo_datas.items()}

    # 检查NRDUCELL
    print("\n=== 测试单值参数核查 ===")
    nrducell_errors = checker.check_single_param(
        mo_datas, 'NRDUCELL', '小区半径(米)', 'TEST_SECTOR'
    )
    # 检查NRCELLALGOSWITCH
    # 测试多值参数核查
    print("\n=== 测试多值参数核查 ===")
    algoswitch_errors = checker.check_multiple_params(
        mo_datas, 'NRCELLALGOSWITCH', ['异频切换算法开关'], 'TEST_SECTOR'
    )

    # 检查NRCELLFREQRELATION漏配和参数验证
    print("\n=== 测试NRCELLFREQRELATION核查 ===")
    nrcellfreq_errors = checker.check_nrcellfreqrelation(mo_datas, 'NRCELLFREQRELATION', 'TEST_SECTOR')
    all_errors = []
    all_errors.extend(nrcellfreq_errors)

    # 处理NRCELLFREQRELATION错误
    for error in nrcellfreq_errors:
        if error['error_type'] == '漏配':
            print(f"漏配信息: {error['message']}")
        elif error['error_type'] == '参数错误':
            print(f"参数错误: {error['message']}")
        else:
            print(f"错误: {error['message']}")
