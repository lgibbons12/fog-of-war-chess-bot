// Minimal observation-only starter. No en passant or castling inference.
#include <cctype>
#include <cstdint>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

struct Move { int from, to, score; bool promotion; };
bool own(char p, bool white) {
    return p != '?' && p != '-' && bool(std::isupper(static_cast<unsigned char>(p))) == white;
}
bool inside(int x, int y) { return x >= 0 && x < 8 && y >= 0 && y < 8; }
std::string coordinate(int square) {
    return std::string(1, char('a' + square % 8)) + char('1' + square / 8);
}
std::vector<Move> candidates(const std::string& board, bool white) {
    std::vector<Move> moves;
    auto add = [&](int from, int to) {
        if (board[to] == '?' || own(board[to], white)) return;
        bool promotion = std::tolower(board[from]) == 'p' && (to / 8 == 0 || to / 8 == 7);
        int score = board[to] == '-' ? 0 : (std::tolower(board[to]) == 'k' ? 1000 : 10);
        moves.push_back({from, to, score + (promotion ? 50 : 0), promotion});
    };
    const int dirs[8][2] = {{1,0},{-1,0},{0,1},{0,-1},{1,1},{1,-1},{-1,1},{-1,-1}};
    const int knights[8][2] = {{1,2},{2,1},{-1,2},{-2,1},{1,-2},{2,-1},{-1,-2},{-2,-1}};
    for (int from = 0; from < 64; ++from) {
        if (!own(board[from], white)) continue;
        int x = from % 8, y = from / 8;
        char kind = char(std::tolower(board[from]));
        if (kind == 'p') {
            int dy = white ? 1 : -1, ny = y + dy;
            if (inside(x, ny) && board[ny*8+x] == '-') {
                add(from, ny*8+x);
                if (y == (white ? 1 : 6) && board[(y+2*dy)*8+x] == '-') add(from, (y+2*dy)*8+x);
            }
            for (int dx : {-1, 1}) if (inside(x+dx, ny)) {
                int to = ny*8+x+dx;
                if (board[to] != '-' && board[to] != '?' && !own(board[to], white)) add(from, to);
            }
        } else if (kind == 'n') {
            for (auto& d : knights) if (inside(x+d[0], y+d[1])) add(from, (y+d[1])*8+x+d[0]);
        } else {
            for (int i = 0; i < 8; ++i) {
                if ((kind == 'b' && i < 4) || (kind == 'r' && i >= 4)) continue;
                int nx = x + dirs[i][0], ny = y + dirs[i][1];
                while (inside(nx, ny)) {
                    int to = ny*8+nx;
                    add(from, to);
                    if (board[to] != '-' || kind == 'k') break;
                    nx += dirs[i][0]; ny += dirs[i][1];
                }
            }
        }
    }
    return moves;
}
int main() {
    std::string line, board;
    if (!std::getline(std::cin, line) || line != "fow") return 1;
    if (!std::getline(std::cin, line)) return 1;
    bool white = !line.empty() && line[0] == 'w';
    uint32_t random = 67980;
    std::cout << "ready" << std::endl;
    while (std::getline(std::cin, line)) {
        if (line.size() == 64) { board = line; continue; }
        std::istringstream clock(line); double seconds; char trailing;
        if (!(clock >> seconds) || (clock >> trailing) || board.empty()) continue;
        auto moves = candidates(board, white);
        if (moves.empty()) return 0;
        Move best = moves.front(); int score = -1;
        for (auto move : moves) {
            random ^= random << 13; random ^= random >> 17; random ^= random << 5;
            int value = move.score * 1024 + int(random % 1024);
            if (value > score) { best = move; score = value; }
        }
        std::cout << "move " << coordinate(best.from) << coordinate(best.to)
                  << (best.promotion ? "q" : "") << std::endl;
    }
}
