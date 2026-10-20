// Minimal observation-only starter. No en passant or castling inference.
use std::io::{self, BufRead, Write};

#[derive(Clone, Copy)]
struct Move { from: usize, to: usize, score: u32, promotion: bool }
fn own(p: u8, white: bool) -> bool {
    p != b'?' && p != b'-' && p.is_ascii_uppercase() == white
}
fn inside(x: i32, y: i32) -> bool { (0..8).contains(&x) && (0..8).contains(&y) }
fn add(out: &mut Vec<Move>, board: &[u8], white: bool, from: usize, to: usize) {
    if board[to] == b'?' || own(board[to], white) { return; }
    let promotion = board[from].to_ascii_lowercase() == b'p' && (to / 8 == 0 || to / 8 == 7);
    let score = if board[to] == b'-' { 0 } else if board[to].to_ascii_lowercase() == b'k' { 1000 } else { 10 };
    out.push(Move {from, to, score: score + if promotion {50} else {0}, promotion});
}
fn candidates(board: &[u8], white: bool) -> Vec<Move> {
    let mut out = Vec::new();
    let dirs = [(1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)];
    let knights = [(1,2),(2,1),(-1,2),(-2,1),(1,-2),(2,-1),(-1,-2),(-2,-1)];
    for from in 0..64 {
        if !own(board[from], white) { continue; }
        let (x, y) = ((from % 8) as i32, (from / 8) as i32);
        let kind = board[from].to_ascii_lowercase();
        if kind == b'p' {
            let dy = if white {1} else {-1}; let ny = y + dy;
            if inside(x, ny) && board[(ny*8+x) as usize] == b'-' {
                add(&mut out, board, white, from, (ny*8+x) as usize);
                if y == if white {1} else {6} && board[((y+2*dy)*8+x) as usize] == b'-' {
                    add(&mut out, board, white, from, ((y+2*dy)*8+x) as usize);
                }
            }
            for dx in [-1, 1] {
                if inside(x+dx, ny) {
                    let to = (ny*8+x+dx) as usize;
                    if board[to] != b'-' && board[to] != b'?' && !own(board[to], white) {
                        add(&mut out, board, white, from, to);
                    }
                }
            }
        } else if kind == b'n' {
            for (dx,dy) in knights { if inside(x+dx,y+dy) {
                add(&mut out, board, white, from, ((y+dy)*8+x+dx) as usize);
            }}
        } else {
            for (i,(dx,dy)) in dirs.iter().enumerate() {
                if (kind == b'b' && i < 4) || (kind == b'r' && i >= 4) { continue; }
                let (mut nx, mut ny) = (x+dx, y+dy);
                while inside(nx,ny) {
                    let to = (ny*8+nx) as usize; add(&mut out, board, white, from, to);
                    if board[to] != b'-' || kind == b'k' { break; }
                    nx += dx; ny += dy;
                }
            }
        }
    }
    out
}
fn coordinate(square: usize) -> String {
    format!("{}{}", (b'a' + (square % 8) as u8) as char, (b'1' + (square / 8) as u8) as char)
}
fn main() -> io::Result<()> {
    let stdin = io::stdin(); let mut lines = stdin.lock().lines();
    if lines.next().transpose()?.as_deref() != Some("fow") { return Ok(()); }
    let color = lines.next().transpose()?.unwrap_or_default(); let white = color.starts_with('w');
    let mut board = Vec::new(); let mut random = 67980u32;
    println!("ready");
    io::stdout().flush()?;
    for line in lines {
        let line = line?;
        if line.len() == 64 { board = line.into_bytes(); continue; }
        if line.parse::<f64>().is_err() || board.is_empty() { continue; }
        let moves = candidates(&board, white); if moves.is_empty() { return Ok(()); }
        let mut best = moves[0]; let mut best_score = 0;
        for m in moves {
            random ^= random << 13; random ^= random >> 17; random ^= random << 5;
            let score = m.score * 1024 + random % 1024;
            if score >= best_score { best = m; best_score = score; }
        }
        println!("move {}{}{}", coordinate(best.from), coordinate(best.to), if best.promotion {"q"} else {""});
        io::stdout().flush()?;
    }
    Ok(())
}
