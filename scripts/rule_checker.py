#!/usr/bin/env python3
"""
规则自查脚本 - 检查规则中域名的连通性
"""

import os
import sys
import json
import time
import random
import socket
import concurrent.futures
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Tuple
from urllib.parse import urlparse

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from config.settings import Config
except ImportError as e:
    print(f"❌ 导入配置失败: {e}")
    sys.exit(1)

class RuleChecker:
    """规则检查器 - 检查域名连通性"""
    
    def __init__(self):
        self.stats = {
            'total_checked': 0,
            'reachable': 0,
            'unreachable': 0,
            'avg_response_time': 0,
            'check_start': None,
            'check_end': None,
            'check_duration': 0
        }
        self.results = []
        
    def extract_domains_from_file(self, filepath: str) -> List[str]:
        """从规则文件中提取域名"""
        domains = set()
        
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                
            # 分割行并处理
            lines = content.split('\n')
            for line in lines:
                line = line.strip()
                if not line or line.startswith(('!', '#', '/')):
                    continue
                
                # 处理Adblock规则
                if line.startswith('||') and '^' in line:
                    # ||example.com^
                    domain = line[2:].split('^')[0].strip()
                    if domain and '.' in domain:
                        domains.add(domain)
                        
                # 处理hosts规则
                elif line.startswith(('0.0.0.0', '127.0.0.1')):
                    # 0.0.0.0 example.com
                    parts = line.split()
                    if len(parts) >= 2:
                        domain = parts[1].strip()
                        if domain and '.' in domain:
                            domains.add(domain)
                            
                # 处理纯域名
                elif '.' in line and ' ' not in line and not line.startswith(('|', '/', '*')):
                    # example.com
                    domain = line.split('#')[0].strip()
                    if domain and '.' in domain:
                        domains.add(domain)
                        
        except Exception as e:
            print(f"  ❌ 读取文件 {filepath} 失败: {e}")
            
        return list(domains)
    
    def check_domain_reachability(self, domain: str) -> Dict:
        """检查单个域名的连通性"""
        start_time = time.time()
        
        # 方法1: 尝试DNS解析
        dns_resolved = False
        try:
            socket.gethostbyname(domain)
            dns_resolved = True
        except socket.gaierror:
            pass
        except Exception:
            pass
        
        # 方法2: 尝试建立TCP连接（HTTP端口80）
        tcp_reachable = False
        if dns_resolved:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(Config.RULE_CHECK_TIMEOUT)
                result = sock.connect_ex((domain, 80))
                sock.close()
                tcp_reachable = (result == 0)
            except Exception:
                pass
        
        response_time = round((time.time() - start_time) * 1000, 2)  # 毫秒
        
        status = "reachable" if (dns_resolved or tcp_reachable) else "unreachable"
        
        return {
            'domain': domain,
            'status': status,
            'dns_resolved': dns_resolved,
            'tcp_reachable': tcp_reachable,
            'response_time_ms': response_time,
            'checked_at': datetime.now().isoformat()
        }
    
    def sample_domains(self, domains: List[str]) -> List[str]:
        """抽样域名用于检查"""
        if not domains:
            return []
            
        total = len(domains)
        
        # 计算抽样数量
        sample_count = max(
            Config.RULE_CHECK_MIN_SAMPLE,
            min(
                Config.RULE_CHECK_MAX_SAMPLE,
                int(total * Config.RULE_CHECK_SAMPLE_PERCENT / 100)
            )
        )
        
        if total <= sample_count:
            return domains
            
        return random.sample(domains, sample_count)
    
    def check_rules_file(self, filepath: str) -> Dict:
        """检查规则文件"""
        filename = Path(filepath).name
        print(f"  🔍 检查文件: {filename}")
        
        # 提取域名
        domains = self.extract_domains_from_file(filepath)
        print(f"    提取到 {len(domains)} 个域名")
        
        if not domains:
            return {
                'file': filename,
                'total_domains': 0,
                'checked_domains': 0,
                'reachable': 0,
                'unreachable': 0,
                'reachability_rate': 0,
                'avg_response_time': 0,
                'results': []
            }
        
        # 抽样
        sampled_domains = self.sample_domains(domains)
        print(f"    抽样 {len(sampled_domains)} 个域名进行检查")
        
        # 并发检查
        check_results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=Config.RULE_CHECK_CONCURRENCY) as executor:
            future_to_domain = {executor.submit(self.check_domain_reachability, domain): domain 
                              for domain in sampled_domains}
            
            completed = 0
            for future in concurrent.futures.as_completed(future_to_domain):
                domain = future_to_domain[future]
                try:
                    result = future.result()
                    check_results.append(result)
                except Exception as e:
                    check_results.append({
                        'domain': domain,
                        'status': 'error',
                        'error': str(e),
                        'checked_at': datetime.now().isoformat()
                    })
                
                completed += 1
                if completed % 10 == 0:
                    print(f"    已检查 {completed}/{len(sampled_domains)} 个域名")
        
        # 统计结果
        reachable = [r for r in check_results if r.get('status') == 'reachable']
        unreachable = [r for r in check_results if r.get('status') == 'unreachable']
        response_times = [r.get('response_time_ms', 0) for r in reachable]
        avg_response_time = round(sum(response_times) / len(response_times), 2) if response_times else 0
        
        reachability_rate = round(len(reachable) / len(check_results) * 100, 2) if check_results else 0
        
        print(f"    检查结果: {len(reachable)} 可达, {len(unreachable)} 不可达, 可达率: {reachability_rate}%")
        
        return {
            'file': filename,
            'total_domains': len(domains),
            'checked_domains': len(check_results),
            'reachable': len(reachable),
            'unreachable': len(unreachable),
            'reachability_rate': reachability_rate,
            'avg_response_time': avg_response_time,
            'sample_size_percent': Config.RULE_CHECK_SAMPLE_PERCENT,
            'results': check_results[:20]  # 只保存前20个结果
        }
    
    def run_checks(self):
        """运行所有检查"""
        print("=" * 60)
        print("🔍 开始规则自查（域名连通性检查）")
        print("=" * 60)
        
        self.stats['check_start'] = datetime.now().isoformat()
        start_time = time.time()
        
        # 检查输出目录
        output_dir = Path(Config.OUTPUT_DIR)
        if not output_dir.exists():
            print("❌ 输出目录不存在，请先运行规则处理")
            return False
        
        # 查找所有规则文件
        rule_files = list(output_dir.glob("*.txt"))
        if not rule_files:
            print("❌ 未找到规则文件")
            return False
        
        # 创建检查报告目录
        check_dir = Path(Config.CHECK_DIR)
        check_dir.mkdir(exist_ok=True)
        
        # 检查每个文件
        all_results = []
        for filepath in rule_files:
            result = self.check_rules_file(str(filepath))
            all_results.append(result)
            
            # 更新总统计
            self.stats['total_checked'] += result['checked_domains']
            self.stats['reachable'] += result['reachable']
            self.stats['unreachable'] += result['unreachable']
        
        # 计算总统计
        elapsed = time.time() - start_time
        self.stats['check_end'] = datetime.now().isoformat()
        self.stats['check_duration'] = round(elapsed, 2)
        
        if self.stats['total_checked'] > 0:
            self.stats['avg_response_time'] = round(
                sum(r['avg_response_time'] for r in all_results) / len(all_results), 2
            )
        
        # 保存详细报告
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = check_dir / f"rule_check_{timestamp}.json"
        
        full_report = {
            'metadata': {
                'check_time': datetime.now().isoformat(),
                'check_duration_seconds': self.stats['check_duration'],
                'config': {
                    'sample_percent': Config.RULE_CHECK_SAMPLE_PERCENT,
                    'timeout': Config.RULE_CHECK_TIMEOUT,
                    'concurrency': Config.RULE_CHECK_CONCURRENCY,
                    'min_sample': Config.RULE_CHECK_MIN_SAMPLE,
                    'max_sample': Config.RULE_CHECK_MAX_SAMPLE
                }
            },
            'summary': self.stats,
            'file_results': all_results
        }
        
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(full_report, f, indent=2, ensure_ascii=False)
        
        # 生成简化Markdown报告
        self._generate_markdown_report(full_report, timestamp)
        
        # 打印总结
        print("\n" + "=" * 60)
        print("📊 规则自查完成")
        print("=" * 60)
        print(f"📈 检查统计:")
        print(f"   总检查域名: {self.stats['total_checked']} 个")
        print(f"   可达域名: {self.stats['reachable']} 个")
        print(f"   不可达域名: {self.stats['unreachable']} 个")
        
        if self.stats['total_checked'] > 0:
            reachability_rate = round(self.stats['reachable'] / self.stats['total_checked'] * 100, 2)
            print(f"   综合可达率: {reachability_rate}%")
        
        print(f"   平均响应时间: {self.stats['avg_response_time']}ms")
        print(f"   总耗时: {self.stats['check_duration']}秒")
        print(f"   详细报告: {report_file}")
        
        # 警告：如果可达率过低
        if self.stats['total_checked'] > 0:
            reachability_rate = self.stats['reachable'] / self.stats['total_checked'] * 100
            if reachability_rate < 60:
                print(f"\n⚠️  警告: 规则可达率较低 ({reachability_rate:.1f}%)")
                print("   建议检查规则源是否包含过多失效域名")
        
        return True
    
    def _generate_markdown_report(self, report_data, timestamp):
        """生成Markdown格式的简化报告"""
        try:
            check_dir = Path(Config.CHECK_DIR)
            md_file = check_dir / f"rule_check_report_{timestamp}.md"
            
            summary = report_data['summary']
            file_results = report_data['file_results']
            
            with open(md_file, 'w', encoding='utf-8') as f:
                f.write("# 📊 广告规则连通性检查报告\n\n")
                f.write(f"**生成时间**: {report_data['metadata']['check_time']}\n")
                f.write(f"**检查耗时**: {summary['check_duration']}秒\n\n")
                
                f.write("## 总体统计\n\n")
                f.write(f"- **检查域名总数**: {summary['total_checked']:,}\n")
                f.write(f"- **可达域名**: {summary['reachable']:,}\n")
                f.write(f"- **不可达域名**: {summary['unreachable']:,}\n")
                
                if summary['total_checked'] > 0:
                    reachability_rate = summary['reachable'] / summary['total_checked'] * 100
                    f.write(f"- **综合可达率**: {reachability_rate:.2f}%\n")
                
                f.write(f"- **平均响应时间**: {summary['avg_response_time']}ms\n\n")
                
                f.write("## 各文件检查结果\n\n")
                for file_result in file_results:
                    f.write(f"### 📄 {file_result['file']}\n\n")
                    f.write(f"- **总域名数**: {file_result['total_domains']:,}\n")
                    f.write(f"- **抽样检查数**: {file_result['checked_domains']:,}\n")
                    f.write(f"- **可达数**: {file_result['reachable']:,}\n")
                    f.write(f"- **不可达数**: {file_result['unreachable']:,}\n")
                    f.write(f"- **可达率**: {file_result['reachability_rate']}%\n")
                    f.write(f"- **平均响应时间**: {file_result['avg_response_time']}ms\n\n")
                
                f.write("## 检查配置\n\n")
                config = report_data['metadata']['config']
                f.write(f"- **抽样比例**: {config['sample_percent']}%\n")
                f.write(f"- **检查超时**: {config['timeout']}秒\n")
                f.write(f"- **并发数**: {config['concurrency']}\n")
                f.write(f"- **最小样本**: {config['min_sample']}\n")
                f.write(f"- **最大样本**: {config['max_sample']}\n\n")
                
                f.write("---\n")
                f.write("*报告由智能广告规则自动化系统生成*\n")
            
            print(f"  📋 Markdown报告已生成: {md_file}")
            
        except Exception as e:
            print(f"  ⚠️  生成Markdown报告失败: {e}")

def main():
    """主函数"""
    if not Config.RULE_CHECK_ENABLED:
        print("规则自查功能已禁用")
        return 0
    
    checker = RuleChecker()
    success = checker.run_checks()
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
