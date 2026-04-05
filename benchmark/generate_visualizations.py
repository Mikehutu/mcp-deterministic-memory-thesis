"""
Generate Benchmark Visualization Charts.

Creates publication-ready charts for thesis from benchmark results:
1. Accuracy comparison (bar chart)
2. Latency comparison (bar chart with p50/p95/p99)
3. Cost comparison (bar chart)
4. Combined performance matrix (heatmap style)
"""

import json
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from pathlib import Path

# Set style for publication-quality figures
plt.style.use('seaborn-v0_8-whitegrid')
plt.rcParams['font.family'] = 'DejaVu Sans'
plt.rcParams['font.size'] = 11
plt.rcParams['axes.labelsize'] = 12
plt.rcParams['axes.titlesize'] = 14
plt.rcParams['figure.titlesize'] = 16


def load_benchmark_results(path: str = "benchmark/results/benchmark_results_expanded.json") -> dict:
    """Load benchmark results from JSON file."""
    with open(path, 'r') as f:
        return json.load(f)


def create_accuracy_chart(results: dict, output_dir: Path):
    """Create accuracy comparison bar chart."""
    systems = []
    exact_matches = []
    semantic_matches = []
    
    for name, data in results['systems'].items():
        if data['accuracy']['queries_total'] > 0:  # Skip systems with no data
            systems.append(name.replace(' (', '\n('))
            exact_rate = float(data['accuracy']['exact_match_rate'].rstrip('%'))
            semantic_rate = float(data['accuracy']['semantic_match_rate'].rstrip('%'))
            exact_matches.append(exact_rate)
            semantic_matches.append(semantic_rate)
    
    x = np.arange(len(systems))
    width = 0.35
    
    fig, ax = plt.subplots(figsize=(10, 6))
    bars1 = ax.bar(x - width/2, exact_matches, width, label='Exact Match', color='#2ecc71', edgecolor='black')
    bars2 = ax.bar(x + width/2, semantic_matches, width, label='Semantic Match', color='#3498db', edgecolor='black')
    
    ax.set_ylabel('Accuracy (%)')
    ax.set_title('Memory System Accuracy Comparison\n(340 Statistical Queries)', fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(systems)
    ax.set_ylim(0, 105)
    ax.legend(loc='upper right')
    ax.axhline(y=100, color='gray', linestyle='--', alpha=0.5)
    
    # Add value labels on bars
    for bar in bars1:
        height = bar.get_height()
        ax.annotate(f'{height:.1f}%',
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 3),
                    textcoords="offset points",
                    ha='center', va='bottom', fontsize=10, fontweight='bold')
    
    for bar in bars2:
        height = bar.get_height()
        ax.annotate(f'{height:.1f}%',
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 3),
                    textcoords="offset points",
                    ha='center', va='bottom', fontsize=10)
    
    plt.tight_layout()
    fig.savefig(output_dir / 'accuracy_comparison.png', dpi=300, bbox_inches='tight')
    fig.savefig(output_dir / 'accuracy_comparison.svg', bbox_inches='tight')
    plt.close(fig)
    print(f"✓ Saved accuracy_comparison.png/svg")


def create_latency_chart(results: dict, output_dir: Path):
    """Create latency comparison bar chart with percentiles."""
    systems = []
    p50_values = []
    p95_values = []
    p99_values = []
    
    for name, data in results['systems'].items():
        if data['accuracy']['queries_total'] > 0:
            systems.append(name.replace(' (', '\n('))
            p50_values.append(data['retrieval']['p50_latency_ms'])
            p95_values.append(data['retrieval']['p95_latency_ms'])
            p99_values.append(data['retrieval']['p99_latency_ms'])
    
    x = np.arange(len(systems))
    width = 0.25
    
    fig, ax = plt.subplots(figsize=(10, 6))
    bars1 = ax.bar(x - width, p50_values, width, label='P50', color='#27ae60', edgecolor='black')
    bars2 = ax.bar(x, p95_values, width, label='P95', color='#f39c12', edgecolor='black')
    bars3 = ax.bar(x + width, p99_values, width, label='P99', color='#e74c3c', edgecolor='black')
    
    ax.set_ylabel('Latency (ms)')
    ax.set_title('Retrieval Latency Comparison\n(Lower is Better)', fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(systems)
    ax.legend(loc='upper right')
    ax.set_yscale('log')  # Log scale to show both fast and slow systems
    
    # Add value labels
    for bars in [bars1, bars2, bars3]:
        for bar in bars:
            height = bar.get_height()
            if height > 0:
                ax.annotate(f'{height:.1f}',
                            xy=(bar.get_x() + bar.get_width() / 2, height),
                            xytext=(0, 3),
                            textcoords="offset points",
                            ha='center', va='bottom', fontsize=8)
    
    plt.tight_layout()
    fig.savefig(output_dir / 'latency_comparison.png', dpi=300, bbox_inches='tight')
    fig.savefig(output_dir / 'latency_comparison.svg', bbox_inches='tight')
    plt.close(fig)
    print(f"✓ Saved latency_comparison.png/svg")


def create_cost_chart(results: dict, output_dir: Path):
    """Create cost comparison bar chart."""
    systems = []
    costs = []
    tokens = []
    
    for name, data in results['systems'].items():
        if data['accuracy']['queries_total'] > 0:
            systems.append(name.replace(' (', '\n('))
            cost_str = data['cost']['estimated_cost_usd'].lstrip('$')
            costs.append(float(cost_str))
            tokens.append(data['cost']['total_tokens'])
    
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    
    # Cost chart
    colors = ['#2ecc71' if c == 0 else '#e74c3c' for c in costs]
    bars1 = ax1.bar(systems, costs, color=colors, edgecolor='black')
    ax1.set_ylabel('Cost (USD)')
    ax1.set_title('API Cost per Benchmark Run\n(Lower is Better)', fontweight='bold')
    
    for bar in bars1:
        height = bar.get_height()
        ax1.annotate(f'${height:.4f}',
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 3),
                    textcoords="offset points",
                    ha='center', va='bottom', fontsize=10, fontweight='bold')
    
    # Token chart
    colors2 = ['#2ecc71' if t == 0 else '#3498db' for t in tokens]
    bars2 = ax2.bar(systems, tokens, color=colors2, edgecolor='black')
    ax2.set_ylabel('Tokens Used')
    ax2.set_title('Token Usage\n(Lower is Better)', fontweight='bold')
    ax2.set_yscale('log')
    
    for bar in bars2:
        height = bar.get_height()
        if height > 0:
            ax2.annotate(f'{int(height):,}',
                        xy=(bar.get_x() + bar.get_width() / 2, height),
                        xytext=(0, 3),
                        textcoords="offset points",
                        ha='center', va='bottom', fontsize=9)
        else:
            ax2.annotate('0',
                        xy=(bar.get_x() + bar.get_width() / 2, 1),
                        xytext=(0, 3),
                        textcoords="offset points",
                        ha='center', va='bottom', fontsize=9, fontweight='bold')
    
    plt.tight_layout()
    fig.savefig(output_dir / 'cost_comparison.png', dpi=300, bbox_inches='tight')
    fig.savefig(output_dir / 'cost_comparison.svg', bbox_inches='tight')
    plt.close(fig)
    print(f"✓ Saved cost_comparison.png/svg")


def create_summary_table(results: dict, output_dir: Path):
    """Create a summary comparison table as an image."""
    fig, ax = plt.subplots(figsize=(14, 6))
    ax.axis('off')
    
    # Prepare data
    columns = ['System', 'Accuracy', 'P50 Latency', 'P95 Latency', 'Cost', 'Tokens', 'Traceability']
    rows = []
    
    for name, data in results['systems'].items():
        if data['accuracy']['queries_total'] > 0:
            rows.append([
                name,
                data['accuracy']['exact_match_rate'],
                f"{data['retrieval']['p50_latency_ms']:.2f} ms",
                f"{data['retrieval']['p95_latency_ms']:.2f} ms",
                data['cost']['estimated_cost_usd'],
                f"{data['cost']['total_tokens']:,}",
                '✓' if data['traceability']['lineage_available'] else '✗'
            ])
    
    # Create table
    table = ax.table(
        cellText=rows,
        colLabels=columns,
        cellLoc='center',
        loc='center',
        colColours=['#3498db'] * len(columns)
    )
    
    table.auto_set_font_size(False)
    table.set_fontsize(11)
    table.scale(1.2, 1.8)
    
    # Style header
    for i in range(len(columns)):
        table[(0, i)].set_text_props(weight='bold', color='white')
    
    # Color code accuracy cells
    for i, row in enumerate(rows, start=1):
        accuracy = float(row[1].rstrip('%'))
        if accuracy >= 90:
            table[(i, 1)].set_facecolor('#2ecc71')
        elif accuracy >= 50:
            table[(i, 1)].set_facecolor('#f39c12')
        else:
            table[(i, 1)].set_facecolor('#e74c3c')
    
    plt.title('Memory System Benchmark Summary\n10 Municipalities × 34 Metrics × 5 Years = 340 Data Points', 
              fontsize=14, fontweight='bold', pad=20)
    
    fig.savefig(output_dir / 'summary_table.png', dpi=300, bbox_inches='tight')
    fig.savefig(output_dir / 'summary_table.svg', bbox_inches='tight')
    plt.close(fig)
    print(f"✓ Saved summary_table.png/svg")


def create_performance_radar(results: dict, output_dir: Path):
    """Create a radar/spider chart for multi-dimensional comparison."""
    categories = ['Accuracy', 'Speed\n(inverted)', 'Cost\n(inverted)', 'Traceability']
    
    fig, ax = plt.subplots(figsize=(10, 8), subplot_kw=dict(polar=True))
    
    # Number of categories
    N = len(categories)
    angles = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()
    angles += angles[:1]  # Complete the loop
    
    colors = ['#2ecc71', '#e74c3c', '#3498db']
    system_names = []
    
    for idx, (name, data) in enumerate(results['systems'].items()):
        if data['accuracy']['queries_total'] > 0:
            # Normalize values to 0-100 scale
            accuracy = float(data['accuracy']['exact_match_rate'].rstrip('%'))
            
            # Invert latency (lower is better -> higher score)
            max_latency = 500  # Reference max
            latency_score = max(0, 100 - (data['retrieval']['p50_latency_ms'] / max_latency * 100))
            
            # Invert cost (lower is better -> higher score)
            max_cost = 1.0
            cost_str = data['cost']['estimated_cost_usd'].lstrip('$')
            cost_score = max(0, 100 - (float(cost_str) / max_cost * 100))
            
            traceability = float(data['traceability']['source_attribution_rate'].rstrip('%'))
            
            values = [accuracy, latency_score, cost_score, traceability]
            values += values[:1]  # Complete the loop
            
            ax.plot(angles, values, 'o-', linewidth=2, label=name, color=colors[idx % len(colors)])
            ax.fill(angles, values, alpha=0.25, color=colors[idx % len(colors)])
            system_names.append(name)
    
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(categories, size=12)
    ax.set_ylim(0, 105)
    ax.legend(loc='upper right', bbox_to_anchor=(1.3, 1.0))
    
    plt.title('Multi-Dimensional Performance Comparison\n(Higher is Better for All Axes)', 
              fontsize=14, fontweight='bold', y=1.08)
    
    fig.savefig(output_dir / 'performance_radar.png', dpi=300, bbox_inches='tight')
    fig.savefig(output_dir / 'performance_radar.svg', bbox_inches='tight')
    plt.close(fig)
    print(f"✓ Saved performance_radar.png/svg")


def main():
    """Generate all visualizations."""
    print("=" * 60)
    print("GENERATING BENCHMARK VISUALIZATIONS")
    print("=" * 60)
    
    # Load results
    results = load_benchmark_results()
    print(f"Loaded benchmark from: {results['benchmark_date']}")
    print(f"Systems: {list(results['systems'].keys())}")
    
    # Create output directory
    output_dir = Path("docs/figures")
    output_dir.mkdir(exist_ok=True)
    print(f"Output directory: {output_dir}")
    print()
    
    # Generate charts
    create_accuracy_chart(results, output_dir)
    create_latency_chart(results, output_dir)
    create_cost_chart(results, output_dir)
    create_summary_table(results, output_dir)
    create_performance_radar(results, output_dir)
    
    print()
    print("=" * 60)
    print("DONE! All figures saved to docs/figures/")
    print("=" * 60)


if __name__ == "__main__":
    main()
