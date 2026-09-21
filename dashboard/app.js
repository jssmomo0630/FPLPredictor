const $ = (selector) => document.querySelector(selector);
const fmt = (value, digits = 1) => Number(value).toFixed(digits);
let dashboard;

function playerCard(player) {
  const badge = player.is_captain ? 'C' : player.is_vice_captain ? 'VC' : '';
  const node = document.createElement('div');
  node.className = 'player';
  node.innerHTML = `<div class="shirt ${badge ? 'captain' : ''}" data-badge="${badge}"></div>
    <span class="player-name" title="${player.name}">${player.name}</span>
    <span class="player-meta">${fmt(player.expected_points, 2)} xPts · £${fmt(player.price_millions)}m</span>`;
  return node;
}

function renderRankings(report, position = 'ALL') {
  const players = position === 'ALL' ? report.top_players : report.top_by_position[position];
  $('#rankings').innerHTML = players.map((player) => `<tr>
    <td>${player.name}<span class="team">${player.team}</span></td><td>${player.position}</td>
    <td>${fmt(player.price_millions)}</td><td><strong>${fmt(player.expected_points, 2)}</strong></td></tr>`).join('');
  document.querySelectorAll('#position-tabs button').forEach((button) =>
    button.classList.toggle('active', button.dataset.position === position));
}

function renderReview(review) {
  if (!review) {
    $('#review').innerHTML = '<div class="pending"><strong>Review pending.</strong><br>Actual points appear here once FPL marks the gameweek data as final.</div>';
    return;
  }
  $('#review').innerHTML = `<div class="review-grid">
    <div class="review-stat"><span>Predicted XI</span><strong>${fmt(review.fixed_xi_expected_points)}</strong></div>
    <div class="review-stat"><span>Actual XI</span><strong>${fmt(review.fixed_xi_actual_points, 0)}</strong></div>
    <div class="review-stat"><span>Forecast error</span><strong>${review.fixed_xi_error > 0 ? '+' : ''}${fmt(review.fixed_xi_error)}</strong></div>
    <div class="review-stat"><span>All-player MAE</span><strong>${fmt(review.all_players_mae, 2)}</strong></div>
  </div><p class="pending">This is the frozen XI benchmark; it does not simulate autosubs or vice-captain fallback.</p>`;
}

function render(index) {
  const item = dashboard.snapshots[index];
  const report = item.report;
  const top = report.top_players[0];
  $('#projected').textContent = fmt(report.fixed_xi_expected_points);
  $('#cost').textContent = `£${fmt(report.cost_millions)}m`;
  $('#top-score').textContent = fmt(top.expected_points, 2);
  $('#top-name').textContent = top.name;
  $('#solver').textContent = report.solver.solver_status;
  $('#deadline').textContent = `Deadline ${new Date(report.deadline_time).toLocaleString([], {dateStyle: 'medium', timeStyle: 'short'})}`;
  $('#version-note').textContent = `Published ${new Date(report.generated_at_utc).toLocaleString()} · immutable snapshot`;
  $('#method').textContent = report.method;
  $('#review-method').textContent = report.review_method;

  const starters = report.squad.filter((player) => player.role === 'starting_xi');
  const pitch = $('#pitch');
  pitch.innerHTML = '';
  ['GK', 'DEF', 'MID', 'FWD'].forEach((position) => {
    const row = document.createElement('div');
    row.className = 'position-row';
    starters.filter((player) => player.position === position).forEach((player) => row.appendChild(playerCard(player)));
    pitch.appendChild(row);
  });
  const bench = $('#bench');
  bench.innerHTML = '';
  report.squad.filter((player) => player.role !== 'starting_xi')
    .sort((a, b) => a.bench_order - b.bench_order).forEach((player) => bench.appendChild(playerCard(player)));

  renderRankings(report);
  renderReview(item.review);
}

fetch('data/dashboard.json')
  .then((response) => { if (!response.ok) throw new Error(`HTTP ${response.status}`); return response.json(); })
  .then((data) => {
    dashboard = data;
    if (!data.snapshots.length) { $('#empty').hidden = false; return; }
    const selector = $('#snapshot');
    selector.innerHTML = data.snapshots.map((item, index) => {
      const report = item.report;
      const time = new Date(report.generated_at_utc).toLocaleString([], {month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit'});
      return `<option value="${index}">${report.season} · GW${report.gameweek} · ${time}</option>`;
    }).join('');
    selector.disabled = false;
    selector.addEventListener('change', () => render(Number(selector.value)));
    ['ALL', 'GK', 'DEF', 'MID', 'FWD'].forEach((position) => {
      const button = document.createElement('button');
      button.type = 'button'; button.dataset.position = position; button.textContent = position;
      button.addEventListener('click', () => renderRankings(data.snapshots[selector.value].report, position));
      $('#position-tabs').appendChild(button);
    });
    $('#dashboard').hidden = false;
    render(0);
  })
  .catch((error) => {
    $('#empty').hidden = false;
    $('#empty h2').textContent = `Dashboard data could not be loaded: ${error.message}`;
  });
