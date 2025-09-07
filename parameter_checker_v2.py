import pandas as pd
import logging
from typing import Dict, List, Any, Optional, Set, Tuple
import re

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class ParameterCheckerV2:
    """
    重新设计的参数核查器，支持复杂条件表达式和嵌套校验逻辑
    支持：(参数名1=值1 and 参数名2=值2) or (参数名3>值3 and 参数名2!=值2) 等复杂条件
    """

    def __init__(self, knowledge_file="参数知识库.xlsx"):
        """初始化参数核查器"""
        self.parameter_info: Dict[str, Dict[str, Any]] = {}  # 参数信息：{MO名称: {参数名: 参数信息}}
        self.validation_rules: List[Dict[str, Any]] = []  # 校验规则列表
        self.errors: List[Dict[str, Any]] = []
        self.load_knowledge_base(knowledge_file)

    def load_knowledge_base(self, file_path="参数知识库.xlsx") -> bool:
        """从Excel文件加载参数知识库"""
        try:
            # 读取参数信息sheet
            param_df = pd.read_excel(file_path, sheet_name='参数信息', dtype=str)
            
            # 验证参数信息sheet必要列
            param_required = ['MO名称', 'MO描述', '场景类型', '参数名称', '参数ID', '参数类型', '参数含义', '值描述']
            param_missing = [col for col in param_required if col not in param_df.columns]
            if param_missing:
                logger.error(f"参数信息sheet缺少必要列: {param_missing}")
                return False

            # 加载参数信息
            self.parameter_info = {}
            for _, row in param_df.iterrows():
                mo_name = row['MO名称'].strip()
                if mo_name not in self.parameter_info:
                    self.parameter_info[mo_name] = {
                        'mo_description': row['MO描述'].strip(),
                        'scenario': row['场景类型'].strip(),
                        'parameters': {}
                    }
                
                param_name = row['参数名称'].strip()
                self.parameter_info[mo_name]['parameters'][param_name] = {
                    'parameter_id': row['参数ID'].strip(),
                    'parameter_type': row['参数类型'].strip(),
                    'parameter_meaning': row['参数含义'].strip(),
                    'value_description': row['值描述'].strip() if pd.notna(row['值描述']) else ''
                }

            # 读取校验规则sheet
            rules_df = pd.read_excel(file_path, sheet_name='校验规则', dtype=str)
            
            # 验证校验规则sheet必要列
            rules_required = ['规则ID', 'MO名称', '校验类型', '参数组合', '期望值', '筛选条件', '逻辑关系', '执行顺序', '后续规则', '描述']
            rules_missing = [col for col in rules_required if col not in rules_df.columns]
            if rules_missing:
                logger.error(f"校验规则sheet缺少必要列: {rules_missing}")
                return False

            # 加载校验规则
            self.validation_rules = []
            for _, row in rules_df.iterrows():
                rule = {
                    'rule_id': row['规则ID'].strip(),
                    'mo_name': row['MO名称'].strip(),
                    'validation_type': row['校验类型'].strip(),  # 错配 或 漏配
                    'parameter_combination': row['参数组合'].strip(),
                    'expected_value': row['期望值'].strip(),
                    'filter_condition': row['筛选条件'].strip() if pd.notna(row['筛选条件']) else '',
                    'logic_relation': row['逻辑关系'].strip(),  # AND 或 OR
                    'execution_order': int(row['执行顺序']) if row['执行顺序'].isdigit() else 1,
                    'next_rule': row['后续规则'].strip() if pd.notna(row['后续规则']) else '',
                    'description': row['描述'].strip()
                }
                self.validation_rules.append(rule)

            # 按执行顺序排序规则
            self.validation_rules.sort(key=lambda x: (x['mo_name'], x['execution_order']))
            
            logger.info(f"成功加载参数知识库: 参数信息 {len(self.parameter_info)} 个MO, 校验规则 {len(self.validation_rules)} 条")
            return True

        except FileNotFoundError:
            logger.error(f"文件 {file_path} 不存在")
            return False
        except Exception as e:
            logger.error(f"加载参数知识库时发生错误: {str(e)}")
            return False

    def evaluate_complex_condition(self, condition: str, current_params: Dict[str, Any]) -> bool:
        """
        评估复杂条件表达式，支持：
        (参数名1=值1 and 参数名2=值2) or (参数名3>值3 and 参数名2!=值2)
        """
        if not condition:
            return True
            
        try:
            # 预处理：将参数名和值进行标准化
            processed_condition = condition
            
            # 查找所有括号组合
            bracket_pattern = r'\(([^()]+)\)'
            
            def evaluate_bracket_content(match):
                content = match.group(1)
                return str(self.evaluate_simple_conditions(content, current_params))
            
            # 递归处理嵌套括号
            while '(' in processed_condition:
                processed_condition = re.sub(bracket_pattern, evaluate_bracket_content, processed_condition)
            
            # 处理剩余的 or 和 and 逻辑
            return self.evaluate_boolean_expression(processed_condition)
            
        except Exception as e:
            logger.error(f"评估条件表达式错误: {condition}, 错误: {str(e)}")
            return False

    def evaluate_simple_conditions(self, condition: str, current_params: Dict[str, Any]) -> bool:
        """评估简单条件组合，处理 and/or 但不包含括号"""
        # 分割 or 条件
        or_parts = [part.strip() for part in condition.split(' or ')]
        
        for or_part in or_parts:
            # 分割 and 条件
            and_parts = [part.strip() for part in or_part.split(' and ')]
            all_and_true = True
            
            for and_part in and_parts:
                if not self.evaluate_single_condition(and_part, current_params):
                    all_and_true = False
                    break
            
            if all_and_true:
                return True
        
        return False

    def evaluate_single_condition(self, condition: str, current_params: Dict[str, Any]) -> bool:
        """评估单个条件，如：参数名=值 或 参数名>值"""
        # 支持的操作符
        operators = ['!=', '>=', '<=', '=', '>', '<']
        
        for op in operators:
            if op in condition:
                param_name, expected_value = condition.split(op, 1)
                param_name = param_name.strip()
                expected_value = expected_value.strip()
                
                current_value = str(current_params.get(param_name, '')).strip()
                
                # 类型转换
                def try_numeric(val):
                    try:
                        return float(val) if '.' in val else int(val)
                    except:
                        return val
                
                current_val = try_numeric(current_value)
                expected_val = try_numeric(expected_value)
                
                # 执行比较
                if op == '=':
                    return current_val == expected_val
                elif op == '!=':
                    return current_val != expected_val
                elif op == '>':
                    return current_val > expected_val
                elif op == '<':
                    return current_val < expected_val
                elif op == '>=':
                    return current_val >= expected_val
                elif op == '<=':
                    return current_val <= expected_val
        
        return False

    def evaluate_boolean_expression(self, expression: str) -> bool:
        """评估布尔表达式，只包含True、False、and、or"""
        try:
            # 安全地评估包含True、False、and、or的表达式
            # 替换为Python的逻辑运算符
            python_expr = expression.replace(' and ', ' and ').replace(' or ', ' or ')
            return eval(python_expr)
        except:
            return False

    def parse_multi_value_parameter(self, value_str: str) -> Dict[str, str]:
        """解析多值参数：k1:开&k2:开&k3:关"""
        result = {}
        if isinstance(value_str, str):
            parts = value_str.split('&')
            for part in parts:
                if ':' in part:
                    key, val = part.split(':', 1)
                    result[key.strip()] = val.strip()
        return result

    def check_parameter_validation(self, groups: Dict[str, pd.DataFrame], mo_name: str, sector_id: str) -> List[Dict[str, Any]]:
        """执行参数校验，支持复杂的嵌套逻辑"""
        errors = []
        
        # 获取该MO的所有校验规则
        mo_rules = [rule for rule in self.validation_rules if rule['mo_name'] == mo_name]
        if not mo_rules:
            logger.warning(f"MO {mo_name} 没有配置校验规则")
            return errors
            
        if mo_name not in groups:
            errors.append({
                'sector_id': sector_id,
                'mo_name': mo_name,
                'error_type': '数据不存在',
                'message': f'{mo_name}数据不存在',
                'rule_id': 'SYSTEM',
                'current_value': None,
                'expected_value': None
            })
            return errors

        mo_data = groups[mo_name]
        
        # 按执行顺序执行规则
        executed_rules = set()
        
        for rule in mo_rules:
            if rule['rule_id'] in executed_rules:
                continue
                
            rule_errors = self.execute_validation_rule(rule, mo_data, sector_id)
            errors.extend(rule_errors)
            executed_rules.add(rule['rule_id'])
            
            # 检查是否有后续规则需要执行
            next_rule_id = rule.get('next_rule', '')
            if next_rule_id:
                next_rule = next((r for r in mo_rules if r['rule_id'] == next_rule_id), None)
                if next_rule and next_rule['rule_id'] not in executed_rules:
                    next_errors = self.execute_validation_rule(next_rule, mo_data, sector_id)
                    errors.extend(next_errors)
                    executed_rules.add(next_rule['rule_id'])
        
        return errors

    def execute_validation_rule(self, rule: Dict[str, Any], mo_data: pd.DataFrame, sector_id: str) -> List[Dict[str, Any]]:
        """执行单个校验规则"""
        errors = []
        
        # 根据筛选条件过滤数据
        filtered_data = mo_data
        if rule['filter_condition']:
            filtered_indices = []
            for idx, row in mo_data.iterrows():
                row_params = row.to_dict()
                if self.evaluate_complex_condition(rule['filter_condition'], row_params):
                    filtered_indices.append(idx)
            filtered_data = mo_data.loc[filtered_indices] if filtered_indices else pd.DataFrame()
        
        if filtered_data.empty:
            if rule['validation_type'] == '漏配':
                errors.append({
                    'sector_id': sector_id,
                    'mo_name': rule['mo_name'],
                    'error_type': '漏配',
                    'message': f"未找到满足筛选条件的数据: {rule['filter_condition']}",
                    'rule_id': rule['rule_id'],
                    'description': rule['description'],
                    'current_value': None,
                    'expected_value': rule['expected_value']
                })
            return errors
        
        # 执行错配或漏配检查
        if rule['validation_type'] == '错配':
            errors.extend(self.check_misconfiguration(rule, filtered_data, sector_id))
        elif rule['validation_type'] == '漏配':
            # 对于漏配检查，如果筛选后有数据说明配置存在，无需报错
            pass
            
        return errors

    def check_misconfiguration(self, rule: Dict[str, Any], filtered_data: pd.DataFrame, sector_id: str) -> List[Dict[str, Any]]:
        """检查错配"""
        errors = []
        param_combination = rule['parameter_combination']
        expected_value = rule['expected_value']
        
        # 获取参数信息
        mo_params = self.parameter_info.get(rule['mo_name'], {}).get('parameters', {})
        
        for idx, row in filtered_data.iterrows():
            row_params = row.to_dict()
            
            # 检查参数组合
            if '&' in param_combination:
                # 多个参数组合检查
                param_names = [p.strip() for p in param_combination.split('&')]
                all_match = True
                error_details = []
                
                for param_name in param_names:
                    if param_name in row_params:
                        param_info = mo_params.get(param_name, {})
                        current_value = str(row_params[param_name]).strip()
                        
                        # 根据参数类型处理
                        if param_info.get('parameter_type') == 'multiple':
                            # 多值参数检查
                            if not self.check_multi_value_match(current_value, expected_value, param_name):
                                all_match = False
                                error_details.append({
                                    'param_name': param_name,
                                    'current_value': current_value,
                                    'expected_value': expected_value,
                                    'param_type': 'multiple'
                                })
                        else:
                            # 单值参数检查
                            if current_value != expected_value:
                                all_match = False
                                error_details.append({
                                    'param_name': param_name,
                                    'current_value': current_value,
                                    'expected_value': expected_value,
                                    'param_type': 'single'
                                })
                
                if not all_match:
                    errors.append({
                        'sector_id': sector_id,
                        'mo_name': rule['mo_name'],
                        'error_type': '错配',
                        'message': f"参数组合配置错误: {param_combination}",
                        'rule_id': rule['rule_id'],
                        'description': rule['description'],
                        'error_details': error_details,
                        'expected_value': expected_value
                    })
            else:
                # 单个参数检查
                param_name = param_combination.strip()
                if param_name in row_params:
                    param_info = mo_params.get(param_name, {})
                    current_value = str(row_params[param_name]).strip()
                    
                    match = False
                    if param_info.get('parameter_type') == 'multiple':
                        match = self.check_multi_value_match(current_value, expected_value, param_name)
                    else:
                        match = (current_value == expected_value)
                    
                    if not match:
                        errors.append({
                            'sector_id': sector_id,
                            'mo_name': rule['mo_name'],
                            'error_type': '错配',
                            'message': f"参数配置错误: {param_name}",
                            'rule_id': rule['rule_id'],
                            'description': rule['description'],
                            'param_name': param_name,
                            'current_value': current_value,
                            'expected_value': expected_value
                        })
        
        return errors

    def check_multi_value_match(self, current_value: str, expected_value: str, param_name: str) -> bool:
        """检查多值参数是否匹配"""
        current_switches = self.parse_multi_value_parameter(current_value)
        expected_switches = self.parse_multi_value_parameter(expected_value)
        
        # 检查所有期望的开关状态是否匹配
        for switch_name, expected_state in expected_switches.items():
            current_state = current_switches.get(switch_name, '')
            if current_state != expected_state:
                return False
        
        return True

    def create_sample_excel(self, file_path="参数知识库.xlsx"):
        """创建示例Excel文件，展示新的双sheet结构"""
        
        # Sheet1: 参数信息
        param_info_data = [
            {
                'MO名称': 'NRDUCELL',
                'MO描述': 'NR DU小区',
                '场景类型': '空域配置',
                '参数名称': '小区半径',
                '参数ID': 'CellRadius',
                '参数类型': 'single',
                '参数含义': '小区覆盖半径，单位为米',
                '值描述': ''
            },
            {
                'MO名称': 'NRCELLALGOSWITCH',
                'MO描述': 'NR小区算法开关',
                '场景类型': '空域配置',
                '参数名称': '异频切换算法开关',
                '参数ID': 'InterFreqHoSwitch',
                '参数类型': 'multiple',
                '参数含义': '异频切换相关算法开关组',
                '值描述': '基于覆盖的异频切换开关:控制基于覆盖的异频切换功能;异频重定向开关:控制异频重定向功能'
            },
            {
                'MO名称': 'NRINTERRATHOPARAM',
                'MO描述': 'NR异频切换参数',
                '场景类型': '空域配置',
                '参数名称': 'CC值',
                '参数ID': 'CCValue',
                '参数类型': 'single',
                '参数含义': '切换控制参数',
                '值描述': ''
            },
            {
                'MO名称': 'NRCELLFREQRELATION',
                'MO描述': 'NR小区频率关系',
                '场景类型': '空域配置',
                '参数名称': '邻区类型',
                '参数ID': 'NeighborType',
                '参数类型': 'single',
                '参数含义': '邻区类型定义',
                '值描述': ''
            },
            {
                'MO名称': 'NRCELLFREQRELATION',
                'MO描述': 'NR小区频率关系',
                '场景类型': '空域配置',
                '参数名称': '载波频点',
                '参数ID': 'CarrierFreq',
                '参数类型': 'single',
                '参数含义': '载波频点值',
                '值描述': ''
            }
        ]
        
        # Sheet2: 校验规则 - 展示复杂条件表达式
        validation_rules_data = [
            {
                '规则ID': 'RULE001',
                'MO名称': 'NRDUCELL',
                '校验类型': '错配',
                '参数组合': '小区半径',
                '期望值': '8000',
                '筛选条件': '',
                '逻辑关系': 'AND',
                '执行顺序': 1,
                '后续规则': '',
                '描述': '小区半径应为8000米'
            },
            {
                '规则ID': 'RULE002',
                'MO名称': 'NRCELLALGOSWITCH',
                '校验类型': '错配',
                '参数组合': '异频切换算法开关',
                '期望值': '基于覆盖的异频切换开关:开&异频重定向开关:开',
                '筛选条件': '(小区类型=宏站 and 覆盖场景=城区)',
                '逻辑关系': 'AND',
                '执行顺序': 1,
                '后续规则': '',
                '描述': '城区宏站的异频切换开关应为开启状态'
            },
            {
                '规则ID': 'RULE003',
                'MO名称': 'NRINTERRATHOPARAM',
                '校验类型': '错配',
                '参数组合': 'CC值',
                '期望值': 'A',
                '筛选条件': '(频段=N78 and 带宽>=100)',
                '逻辑关系': 'AND',
                '执行顺序': 1,
                '后续规则': 'RULE004',
                '描述': 'N78频段且带宽>=100MHz时CC值应为A'
            },
            {
                '规则ID': 'RULE004',
                'MO名称': 'NRINTERRATHOPARAM',
                '校验类型': '错配',
                '参数组合': 'CC值',
                '期望值': 'B',
                '筛选条件': '(频段=N41 or 带宽<100)',
                '逻辑关系': 'OR',
                '执行顺序': 2,
                '后续规则': '',
                '描述': '或者N41频段或带宽<100MHz时CC值应为B'
            },
            {
                '规则ID': 'RULE005',
                'MO名称': 'NRCELLFREQRELATION',
                '校验类型': '漏配',
                '参数组合': '邻区类型&载波频点',
                '期望值': '同频&2100',
                '筛选条件': '(小区类型=宏站 and 覆盖场景=城区)',
                '逻辑关系': 'AND',
                '执行顺序': 1,
                '后续规则': 'RULE006',
                '描述': '城区宏站必须配置2100MHz同频邻区'
            },
            {
                '规则ID': 'RULE006',
                'MO名称': 'NRCELLFREQRELATION',
                '校验类型': '错配',
                '参数组合': '优先级',
                '期望值': '5',
                '筛选条件': '(邻区类型=同频 and 载波频点=2100)',
                '逻辑关系': 'AND',
                '执行顺序': 2,
                '后续规则': '',
                '描述': '2100MHz同频邻区优先级应为5'
            }
        ]

        # 创建Excel文件
        df_params = pd.DataFrame(param_info_data)
        df_rules = pd.DataFrame(validation_rules_data)

        with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
            df_params.to_excel(writer, sheet_name='参数信息', index=False)
            df_rules.to_excel(writer, sheet_name='校验规则', index=False)

        logger.info(f"新版本参数知识库已生成: {file_path}")
        logger.info("新特性: 支持复杂条件表达式 (param1=value1 and param2=value2) or (param3>value3)")


if __name__ == "__main__":
    # 创建新版本的参数核查器
    checker = ParameterCheckerV2()
    
    # 生成示例Excel文件
    checker.create_sample_excel("参数知识库_v2.xlsx")
    
    # 测试复杂条件表达式评估
    print("\n=== 测试复杂条件表达式 ===")
    test_params = {
        '小区类型': '宏站',
        '覆盖场景': '城区',
        '频段': 'N78',
        '带宽': '100'
    }
    
    # 测试不同的条件表达式
    conditions = [
        "(小区类型=宏站 and 覆盖场景=城区)",
        "(频段=N78 and 带宽>=100)",
        "(频段=N41 or 带宽<100)",
        "(小区类型=宏站 and 覆盖场景=城区) or (频段=N78)"
    ]
    
    for condition in conditions:
        result = checker.evaluate_complex_condition(condition, test_params)
        print(f"条件: {condition}")
        print(f"结果: {result}")
        print("---")