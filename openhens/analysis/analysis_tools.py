
from pathlib import Path
import datetime
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.io as pio

# Constants
MARKER_MIN_SIZE = 5
MARKER_MAX_SIZE = 10
DEFAULT_FONT = "Constantia"
DEFAULT_TEMPLATE = "plotly_white"
GRID_STYLE = dict(gridcolor="rgba(0,0,0,0.3)", gridwidth=1.0, backgroundcolor="rgb(245, 245, 245)")
FIG_SIZE = (1000, 800, 2) # width, height, scale for image export
METRIC_LABELS = {
    "min_dQ": "(dQ/dA)ₘᵢₙ",
    "Solve Time": "Solve Time (s)",
    "dTmin": "ΔTₘᵢₙ (°C)",
    "ESM TAC": "ESM TAC ($/y)"
}  


def get_n_best_by_TAC(P_list: list, n_best: int = 10) -> list:     
    '''
    Sorts case list by TAC and returns top n_best

    Orders the position of each case in the case_list from order of solving to lowest>highest TAC and only returns the user specified n_best. Must be called seperately to class initialisation  
    '''
    P_list = sorted(P_list, key=lambda P: P.case.TAC)
    if n_best == None: n_best = 0
    if n_best > 0:
        P_list = P_list[:n_best]  # returns sorted case list

    return P_list

def save_esm_metrics(P_list, path: Path) -> pd.DataFrame:
    metrics = _collect_esm_metrics(P_list)
    _append_to_excel(path / 'Solution Metrics.xlsx', metrics)
    return metrics

def save_run_summary(P_list, attempted, total_run_time, path: Path) -> None:
    df = _collect_run_summary(P_list, attempted, total_run_time)
    _append_to_excel(path / 'Run Metrics.xlsx', df)

def plot_metric_relationships(metrics: pd.DataFrame, path: Path) -> None:   
    _plot_3d_scatter(metrics, x='min_dQ', y='dTmin', z='ESM TAC', filename="dqda_dTmin_TAC", path=path)
    _plot_3d_scatter(metrics, x='min_dQ', y='dTmin', z='Solve Time', color='ESM TAC', colorbar_title='TAC ($/y)', filename="dqda_dTmin_time_TAC", path=path)
    if len(metrics['Stages'].unique()) > 1: # only plot if there are multiple stages
        _plot_3d_scatter(metrics, x='min_dQ', y='dTmin', z='Stages', color='Solve Time', colorbar_title='Solve Time (s)', filename="dqda_dTmin_stages_Time", path=path)
        _plot_3d_scatter(metrics, x='min_dQ', y='dTmin', z='Stages', color='ESM TAC', colorbar_title='TAC ($/y)', filename="dqda_dTmin_stages_TAC", path=path)

def _append_to_excel(file: Path, data: pd.DataFrame) -> None:
    if file.exists():
        existing = pd.read_excel(file)
        data = pd.concat([existing, data.reset_index(drop=True)], ignore_index=True)
    data.to_excel(file, index=False)

def _collect_esm_metrics(P_list):
    '''Collects the metrics relating to each ESM solution
    
    These metrics are also used to create the 3D plots that compare parameters (dTmin, (dQ/dA)min and stages) with solve time and TAC
    '''
    records = []
    now = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    for P in P_list:
        if P.framework == 'ESM':
            total_solve_time = sum([
                P.case.solve_time,
                P.parent.case.solve_time,
                P.parent.parent.case.solve_time
            ])
            records.append({
                'Date': now,
                'dTmin': P.parent.parent.dTmin,
                'min_dQ': P.parent.min_dqda,
                'Solve Time': total_solve_time,
                'ESM TAC': P.case.TAC,
                'Stages': P.case.stages,
                'N Recovery Units': P.case.n_recovery_units,
                'N CU Units': P.case.n_cu_units,
                'N HU Units': P.case.n_hu_units
            })
    return pd.DataFrame(records)

def _collect_run_summary(P_list, attempted, total_run_time):
    '''Collect summary of the current run
    
    Collects the number and quality of solutions attempted & solved  during the current run.
    '''
    now = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    esm_solutions = [P for P in P_list if P.framework == 'ESM']
    costs = [P.case.TAC for P in esm_solutions]
    quartiles = np.quantile(costs, [0.25, 0.5, 0.75]) if costs else [0, 0, 0]

    sorted_cases = sorted(esm_solutions, key=lambda P: P.case.TAC)
    best_tac = sorted_cases[0].case.TAC if sorted_cases else 0

    thresholds = {f'Within {int(t*100)}%': sum(P.case.TAC <= best_tac * (1 + t) for P in sorted_cases) for t in [0.02, 0.05, 0.10]}

    summary = {
        'Date': [now],
        'Best Solution': best_tac,
        'Total Cases Attempted': attempted,
        'Total Cases Solved': len(P_list) + len(esm_solutions) * 10,
        'Total Run Time (s)': total_run_time,
        'Quartile 1': quartiles[0],
        'Quartile 2': quartiles[1],
        'Quartile 3': quartiles[2],
        **thresholds
    }
    return pd.DataFrame(summary) 

def _plot_3d_scatter(metrics, x, y, z, color=None, colorbar_title=None, filename="3d_plot", path=Path(".")):
    ''' Create a 3D interactive scatter plot using Plotly.'''
    series = metrics[color] if color else metrics[z]
    norm = (series - series.min()) / (series.max() - series.min())
    metrics['marker_size'] = round(MARKER_MIN_SIZE + (1 - norm) * (MARKER_MAX_SIZE - MARKER_MIN_SIZE), 2)

    fig = px.scatter_3d(
        metrics,
        x=x,
        y=y,
        z=z,
        color=color,
        color_continuous_scale='Viridis' if color else None,
        opacity=0.8,
        template=DEFAULT_TEMPLATE
    )

    hover_text = f"{x}: %{{x:.2f}}<br>{y}: %{{y:.2f}}<br>{z}: %{{z:.2f}}"
    if color:
        hover_text += f"<br>{color}: %{{marker.color:.2f}}"

    fig.update_traces(marker=dict(size=metrics['marker_size'], line=dict(width=1, color='black')), hovertemplate=hover_text)
    _apply_3d_layout(fig, x, y, z, colorbar_title)
    _save_plot(fig, path, filename)
 
def _apply_3d_layout(fig, x, y, z, colorbar_title=None):
    x_title = METRIC_LABELS.get(x, x)
    y_title = METRIC_LABELS.get(y, y)
    z_title = METRIC_LABELS.get(z, z)
    layout = dict(
        scene=dict(
            xaxis=dict(title=dict(text=x_title, font=dict(family=DEFAULT_FONT, size=18, color="black")), tickfont=dict(family=DEFAULT_FONT, size=16), **GRID_STYLE),
            yaxis=dict(title=dict(text=y_title, font=dict(family=DEFAULT_FONT, size=18, color="black")), tickfont=dict(family=DEFAULT_FONT, size=16), **GRID_STYLE),
            zaxis=dict(title=dict(text=z_title, font=dict(family=DEFAULT_FONT, size=18, color="black")), tickfont=dict(family=DEFAULT_FONT, size=16), **GRID_STYLE),
            camera=dict(eye=dict(x=1.6, y=1.6, z=0.5)),
            aspectmode='cube'
        ),
        width=1000,
        height=800,
        margin=dict(l=20, r=20, t=20, b=20),
    )
    if colorbar_title:
        layout['coloraxis_colorbar'] = dict(
            title=dict(text=colorbar_title, font=dict(family=DEFAULT_FONT, size=16)),
            tickfont=dict(family=DEFAULT_FONT, size=16),
            tickformat="~s",
            x=0.88,
            len=0.75
        )
    fig.update_layout(**layout)
 
def _save_plot(fig, path: Path, name: str, save: bool = True, show: bool = True) -> None:
    pio.renderers.default = 'browser'  # Opens in your browser
    if save:
        fig.write_html(path / f"{name}.html")
        pio.write_image(fig, path / f"{name}.png", width=FIG_SIZE[0], height=FIG_SIZE[1], scale=FIG_SIZE[2], engine="kaleido") 
    if show:
        fig.show()
    

    

