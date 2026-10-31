/*
  Fairy-Stockfish, a UCI chess variant playing engine derived from Stockfish
  Copyright (C) 2018-2022 Fabian Fichter

  Fairy-Stockfish is free software: you can redistribute it and/or modify
  it under the terms of the GNU General Public License as published by
  the Free Software Foundation, either version 3 of the License, or
  (at your option) any later version.

  Fairy-Stockfish is distributed in the hope that it will be useful,
  but WITHOUT ANY WARRANTY; without even the implied warranty of
  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
  GNU General Public License for more details.

  You should have received a copy of the GNU General Public License
  along with this program.  If not, see <http://www.gnu.org/licenses/>.
*/

#ifndef VARIANT_H_INCLUDED
#define VARIANT_H_INCLUDED

#include <bitset>
#include <cctype>
#include <set>
#include <map>
#include <vector>
#include <algorithm>
#include <string>
#include <functional>
#include <sstream>
#include <iostream>

#include "types.h"
#include "bitboard.h"

namespace Stockfish {

enum PromotionCase : uint16_t {
  PROMO_OIQ = 1 << 0, PROMO_OICU = 1 << 1, PROMO_OICP = 1 << 8,
  PROMO_IIQ = 1 << 2, PROMO_IICU = 1 << 3, PROMO_IICP = 1 << 9,
  PROMO_IOQ = 1 << 4, PROMO_IOCU = 1 << 5, PROMO_IOCP = 1 << 10,
  PROMO_LASTQ = 1 << 6, PROMO_LASTCU = 1 << 7, PROMO_LASTCP = 1 << 11,
  PROMO_OIC = PROMO_OICU | PROMO_OICP,
  PROMO_IIC = PROMO_IICU | PROMO_IICP,
  PROMO_IOC = PROMO_IOCU | PROMO_IOCP,
  PROMO_LASTC = PROMO_LASTCU | PROMO_LASTCP,
  PROMO_OI = PROMO_OIQ | PROMO_OIC,
  PROMO_II = PROMO_IIQ | PROMO_IIC,
  PROMO_IO = PROMO_IOQ | PROMO_IOC,
  PROMO_ALL = PROMO_OI | PROMO_II | PROMO_IO,
  PROMO_LAST = PROMO_LASTQ | PROMO_LASTC
};

enum PromotionRequirement { PROMOTION_OPTIONAL, PROMOTION_MANDATORY };

enum PromotionCapture : uint8_t {
  PROMO_CAPTURE_AUTO = 0, PROMO_CAPTURE_NONE = 1,
  PROMO_CAPTURE_UNPROMOTED = 2, PROMO_CAPTURE_PROMOTED = 4
};

struct PromotionRegionSetting {
  Bitboard region = 0;
  bool specified = false;
  bool builtIn = false;
};

struct PromotionPolicySetting {
  uint16_t cases = 0;
  bool specified = false;
  bool inherit = false;
};

struct PromotionRule {
  Bitboard optionalRegion = 0;
  Bitboard mandatoryRegion = 0;
  uint16_t optionalCases = 0;
  uint16_t mandatoryCases = 0;
};

struct DropRegionSetting {
  Bitboard region = 0;
  bool specified = false;
};

/// Variant struct stores information needed to determine the rules of a variant.

struct HookMoveSpec {
  uint64_t directionPairMask = 0;
  int firstRange = 0;
  int secondRange = 0;
  int captureLimit = 1;
  bool stopOnCapture = false;
};

struct DoubleMoveSpec {
  PieceType firstType = NO_PIECE_TYPE;
  PieceType secondType = NO_PIECE_TYPE;
  int captureLimit = 1;
  bool outwardOnly = false;
};

enum ExtinctionConditionType {
  EXTINCTION_CONDITION_NONE,
  EXTINCTION_CONDITION_PIECE_COUNT,
  EXTINCTION_CONDITION_AND,
  EXTINCTION_CONDITION_OR
};

enum ExtinctionCountComparison {
  EXTINCTION_COUNT_EQUAL,
  EXTINCTION_COUNT_AT_MOST
};

struct ExtinctionCondition {
  ExtinctionConditionType type = EXTINCTION_CONDITION_NONE;
  ExtinctionCountComparison comparison = EXTINCTION_COUNT_EQUAL;
  PieceType pieceType = NO_PIECE_TYPE;
  int count = 0;
  std::vector<ExtinctionCondition> children;
};

enum TradingCategory {
  TRADING_NONE,
  TRADING_ANY,
  TRADING_ADJACENT,
  TRADING_DISTANT,
  TRADING_ADJACENT_2_CAPTURE,
  TRADING_DISTANT_2_CAPTURE,
  TRADING_CATEGORY_NB
};

enum TradingRestriction {
  TRADING_UNRESTRICTED,
  TRADING_IF_RECAPTURABLE,
  TRADING_ALWAYS
};

struct TradingRule {
  TradingCategory category = TRADING_NONE;
  TradingRestriction restriction = TRADING_UNRESTRICTED;
  PieceSet targets = NO_PIECE_SET;
  PieceSet restrictors = NO_PIECE_SET;
};

struct TradingRuleRow {
  std::vector<TradingRule> rules = {};
};

enum ShuffleSquaresMethod {
  SHUFFLE_NONE,
  SHUFFLE_MIRROR,
  SHUFFLE_ROTATE,
  SHUFFLE_PERMUTE,
  SHUFFLE_BB_RKR,
  SHUFFLE_BB
};

struct Variant {
  bool promotionVictimState = false;
  std::string variantTemplate = "fairy";
  std::string pieceToCharTable = "-";
  int pocketSize = 0;
  Rank maxRank = RANK_8;
  File maxFile = FILE_H;
  bool chess960 = false;
  bool twoBoards = false;
  int pieceValue[PHASE_NB][PIECE_TYPE_NB] = {};
  std::string customPiece[CUSTOM_PIECES_NB] = {};
  PieceSet pieceTypes = CHESS_PIECES;
  std::string pieceToChar =  " PNBRQ" + std::string(KING - QUEEN - 1, ' ') + "K" + std::string(PIECE_COLOR_STRIDE - KING - 1, ' ')
                           + " pnbrq" + std::string(KING - QUEEN - 1, ' ') + "k" + std::string(PIECE_COLOR_STRIDE - KING - 1, ' ');
  std::string pieceToCharSynonyms = std::string(PIECE_NB, ' ');
  std::vector<std::string> pieceToSymbol;
  std::vector<std::string> pieceToSymbolSynonyms;
  std::string startFen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";
  std::string shuffleSquaresFenTemplate = "";
  Bitboard shuffleSquares[COLOR_NB] = {};
  ShuffleSquaresMethod shuffleSquaresMethod[COLOR_NB] = {SHUFFLE_NONE, SHUFFLE_NONE};
  Bitboard mobilityRegion[COLOR_NB][PIECE_TYPE_NB] = {};
  Bitboard promotionRegion[COLOR_NB] = {Rank8BB, Rank1BB};
  PieceType mainPromotionPawnType[COLOR_NB] = {PAWN, PAWN};
  PieceSet promotionPawnTypes[COLOR_NB] = {piece_set(PAWN), piece_set(PAWN)};
  PieceSet promotionPieceTypes[COLOR_NB] = {piece_set(QUEEN) | ROOK | BISHOP | KNIGHT,
                                            piece_set(QUEEN) | ROOK | BISHOP | KNIGHT};
  bool sittuyinPromotion = false;
  int promotionLimit[PIECE_TYPE_NB] = {}; // 0 means unlimited
  PieceType promotedPieceType[PIECE_TYPE_NB] = {};
  bool piecePromotionOnCapture = false;
  bool mandatoryPawnPromotion = true;
  bool mandatoryPiecePromotion = false;
  bool pieceDemotion = false;
  bool blastOnCapture = false;
  PieceSet blastImmuneTypes = NO_PIECE_SET;
  PieceSet mutuallyImmuneTypes = NO_PIECE_SET;
  PieceSet petrifyOnCaptureTypes = NO_PIECE_SET;
  bool petrifyBlastPieces = false;
  PieceSet prohibitedCaptures[COLOR_NB][PIECE_TYPE_NB] = {};
  bool hasTradingRules = false;
  bool hasTradingCounterstrike = false;
  bool tradingRuleJcsaConnector = false;
  PieceSet tradingCounterstrikeTargets = NO_PIECE_SET;
  PieceSet tradingRuleAllowCheckers = NO_PIECE_SET;
  uint16_t tradingRuleRowIndex[PIECE_TYPE_NB] = {}; // Stored index plus one; zero means no rule
  std::vector<TradingRuleRow> tradingRuleRows = {};
  uint64_t lionMoveMask[PIECE_TYPE_NB] = {};
  bool lionMoveSpecified[PIECE_TYPE_NB] = {};
  uint64_t lionDogMoveMask[PIECE_TYPE_NB] = {}; // 48 bits: six paths per direction
  bool lionDogMoveSpecified[PIECE_TYPE_NB] = {};
  bool hasLionDog = false;
  bool lionDogConfigurationValid = true;
  bool lionDogMasksCompatible = true;
  uint32_t lionDogPathMask[COLOR_NB][PIECE_TYPE_NB] = {};
  uint64_t combined_lion_mask(PieceType pt) const;
  void resolve_lion_dog_masks();
  uint64_t lionEffectivePathMask[COLOR_NB][PIECE_TYPE_NB][SQUARE_NB] = {};
  std::vector<HookMoveSpec> hookMoveSpecs[PIECE_TYPE_NB] = {};
  std::vector<DoubleMoveSpec> doubleMoveSpecs[PIECE_TYPE_NB] = {};
  bool doubleStep = true;
  Bitboard doubleStepRegion[COLOR_NB] = {Rank2BB, Rank7BB};
  Bitboard tripleStepRegion[COLOR_NB] = {};
  Bitboard enPassantRegion[COLOR_NB] = {AllSquares, AllSquares};
  PieceSet enPassantTypes[COLOR_NB] = {piece_set(PAWN), piece_set(PAWN)};
  bool castling = true;
  bool castlingDroppedPiece = false;
  File castlingKingsideFile = FILE_G;
  File castlingQueensideFile = FILE_C;
  Rank castlingRank = RANK_1;
  File castlingKingFile = FILE_E;
  PieceType castlingKingPiece[COLOR_NB] = {KING, KING};
  File castlingRookKingsideFile = FILE_MAX; // only has to match if rook is not in corner in non-960 variants
  File castlingRookQueensideFile = FILE_A; // only has to match if rook is not in corner in non-960 variants
  PieceSet castlingRookPieces[COLOR_NB] = {piece_set(ROOK), piece_set(ROOK)};
  bool oppositeCastling = false;
  PieceType kingType = KING;
  bool checking = true;
  bool dropChecks = true;
  bool mustCapture = false;
  bool mustDrop = false;
  PieceType mustDropType = ALL_PIECES;
  bool pieceDrops = false;
  bool dropLoop = false;
  bool capturesToHand = false;
  bool firstRankPawnDrops = false;
  bool promotionZonePawnDrops = false;
  EnclosingRule enclosingDrop = NO_ENCLOSING;
  Bitboard enclosingDropStart = 0;
  Bitboard dropRegion[COLOR_NB] = {AllSquares, AllSquares};
  bool sittuyinRookDrop = false;
  bool dropOppositeColoredBishop = false;
  bool dropPromoted = false;
  PieceType dropNoDoubled = NO_PIECE_TYPE;
  int dropNoDoubledCount = 1;
  bool immobilityIllegal = false;
  bool gating = false;
  WallingRule wallingRule = NO_WALLING;
  Bitboard wallingRegion[COLOR_NB] = {AllSquares, AllSquares};
  bool wallOrMove = false;
  bool seirawanGating = false;
  bool cambodianMoves = false;
  Bitboard diagonalLines = 0;
  bool pass[COLOR_NB] = {false, false};
  bool passOnStalemate[COLOR_NB] = {false, false};
  bool makpongRule = false;
  bool flyingGeneral = false;
  Rank soldierPromotionRank = RANK_1;
  EnclosingRule flipEnclosedPieces = NO_ENCLOSING;
  bool freeDrops = false;

  // game end
  PieceSet nMoveRuleTypes[COLOR_NB] = {piece_set(PAWN), piece_set(PAWN)};
  int nMoveRule = 50;
  int nFoldRule = 3;
  Value nFoldValue = VALUE_DRAW;
  bool nFoldValueAbsolute = false;
  bool perpetualCheckIllegal = false;
  bool moveRepetitionIllegal = false;
  ChasingRule chasingRule = NO_CHASING;
  Value stalemateValue = VALUE_DRAW;
  bool stalematePieceCount = false; // multiply stalemate value by sign(count(~stm) - count(stm))
  Value checkmateValue = -VALUE_MATE;
  bool shogiPawnDropMateIllegal = false;
  bool shatarMateRule = false;
  bool bikjangRule = false;
  Value extinctionValue = VALUE_NONE;
  bool extinctionClaim = false;
  bool extinctionPseudoRoyal = false;
  bool dupleCheck = false;
  PieceSet extinctionPieceTypes = NO_PIECE_SET;
  ExtinctionCondition extinctionCondition;
  PieceSet extinctionConditionPieceTypes = NO_PIECE_SET;
  int extinctionPieceCount = 0;
  int extinctionOpponentPieceCount = 0;
  bool baringRule = false;
  Value baringValue = -VALUE_MATE;
  bool baringRuleRoyalTypesAuto = true;
  PieceSet baringRuleRoyalTypes = NO_PIECE_SET;
  PieceSet baringRoyalTypes = NO_PIECE_SET; // Resolved after inheritance
  PieceType flagPiece[COLOR_NB] = {ALL_PIECES, ALL_PIECES};
  Bitboard flagRegion[COLOR_NB] = {};
  int flagPieceCount = 1;
  bool flagPieceBlockedWin = false;
  bool flagMove = false;
  bool flagPieceSafe = false;
  bool checkCounting = false;
  int connectN = 0;
  PieceSet connectPieceTypes = ~NO_PIECE_SET;
  bool connectHorizontal = true;
  bool connectVertical = true;
  bool connectDiagonal = true;
  Bitboard connectRegion1[COLOR_NB] = {};
  Bitboard connectRegion2[COLOR_NB] = {};
  int connectNxN = 0;
  int collinearN = 0;
  Value connectValue = VALUE_MATE;
  MaterialCounting materialCounting = NO_MATERIAL_COUNTING;
  bool adjudicateFullBoard = false;
  CountingRule countingRule = NO_COUNTING;
  CastlingRights castlingWins = NO_CASTLING;

  // Derived properties
  bool fastAttacks = true;
  bool fastAttacks2 = true;
  std::string nnueAlias = "";
  PieceType nnueKing = KING;
  int nnueDimensions;
  bool nnueUsePockets;
  int pieceSquareIndex[COLOR_NB][PIECE_NB];
  int pieceHandIndex[COLOR_NB][PIECE_NB];
  int kingSquareIndex[SQUARE_NB];
  int nnueMaxPieces;
  EndgameEval endgameEval = EG_EVAL_CHESS;
  bool shogiStylePromotions = false;
  std::vector<Direction> connectDirections;
  PieceSet connectPieceTypesTrimmed = ~NO_PIECE_SET;

  // Unresolved settings: type zero is global; colour COLOR_NB is the root.
  PromotionRegionSetting optionalPromotionRegions[COLOR_NB][PIECE_TYPE_NB] = {};
  PromotionRegionSetting mandatoryPromotionRegions[COLOR_NB][PIECE_TYPE_NB] = {};
  PromotionPolicySetting promotionPolicies[COLOR_NB + 1][PIECE_TYPE_NB][2] = {};
  bool legacyPromotionDefaults = true;
  // Built-ins declare their region requirement explicitly; INI compatibility
  // resolves the old pawn/piece flags instead.
  int nativePromotionRequirement[COLOR_NB] = {-1, -1};
  // Flattened rules for choice and fixed-mapping promotion respectively.
  PromotionRule promotionRules[2][COLOR_NB][PIECE_TYPE_NB] = {};
  Bitboard promotionAreas[COLOR_NB][PIECE_TYPE_NB] = {};
  Bitboard promotionCandidates[COLOR_NB][PIECE_TYPE_NB] = {};
  PieceSet lastPromotionTypes[COLOR_NB] = {};
  mutable Bitboard promotionImmobility[COLOR_NB][PIECE_TYPE_NB] = {};
  bool conventionalPawnPromotion[COLOR_NB] = {};
  DropRegionSetting dropRegionOverrides[COLOR_NB][PIECE_TYPE_NB] = {};
  Bitboard dropRegions[COLOR_NB][PIECE_TYPE_NB] = {};
  int xboardDropRanks[PIECE_TYPE_NB] = {};
  bool xboardDropRegionsCompatible = true;

  Variant() {
      pieceToSymbol.resize(PIECE_NB);
      pieceToSymbolSynonyms.resize(PIECE_NB);
      for (Piece p = NO_PIECE; p < PIECE_NB; ++p)
      {
          if (pieceToChar[p] != ' ')
              pieceToSymbol[p] = std::string(1, pieceToChar[p]);
          if (pieceToCharSynonyms[p] != ' ')
              pieceToSymbolSynonyms[p] = std::string(1, pieceToCharSynonyms[p]);
      }
  }

  static std::string black_symbol(std::string s) {
      std::transform(s.begin(), s.end(), s.begin(), [](unsigned char c) { return std::tolower(c); });
      return s;
  }

  static std::string white_symbol(std::string s) {
      std::transform(s.begin(), s.end(), s.begin(), [](unsigned char c) { return std::toupper(c); });
      return s;
  }

  void add_piece(PieceType pt, char c, std::string betza = "", char c2 = ' ') {
      add_piece(pt, std::string(1, c), betza, c2 == ' ' ? "" : std::string(1, c2));
  }

  void add_piece(PieceType pt, std::string symbol, std::string betza = "", std::string symbol2 = "") {
      // Avoid ambiguous definition by removing existing piece with same letter
      size_t idx;
      if (symbol.size() == 1 && (idx = pieceToChar.find(toupper(symbol[0]))) != std::string::npos)
          remove_piece(PieceType(idx));
      // Now add new piece
      pieceToSymbol[make_piece(WHITE, pt)] = white_symbol(symbol);
      pieceToSymbol[make_piece(BLACK, pt)] = black_symbol(symbol);
      pieceToChar[make_piece(WHITE, pt)] = symbol.size() == 1 ? toupper(symbol[0]) : ' ';
      pieceToChar[make_piece(BLACK, pt)] = symbol.size() == 1 ? tolower(symbol[0]) : ' ';
      pieceToSymbolSynonyms[make_piece(WHITE, pt)] = white_symbol(symbol2);
      pieceToSymbolSynonyms[make_piece(BLACK, pt)] = black_symbol(symbol2);
      pieceToCharSynonyms[make_piece(WHITE, pt)] = symbol2.size() == 1 ? toupper(symbol2[0]) : ' ';
      pieceToCharSynonyms[make_piece(BLACK, pt)] = symbol2.size() == 1 ? tolower(symbol2[0]) : ' ';
      pieceTypes |= pt;
      // Add betza notation for custom piece
      if (is_custom(pt))
          customPiece[pt - CUSTOM_PIECES] = betza;
  }

  void add_piece(PieceType pt, char c, char c2) {
      add_piece(pt, c, "", c2);
  }

  void remove_piece(PieceType pt) {
      pieceToChar[make_piece(WHITE, pt)] = ' ';
      pieceToChar[make_piece(BLACK, pt)] = ' ';
      pieceToCharSynonyms[make_piece(WHITE, pt)] = ' ';
      pieceToCharSynonyms[make_piece(BLACK, pt)] = ' ';
      pieceToSymbol[make_piece(WHITE, pt)].clear();
      pieceToSymbol[make_piece(BLACK, pt)].clear();
      pieceToSymbolSynonyms[make_piece(WHITE, pt)].clear();
      pieceToSymbolSynonyms[make_piece(BLACK, pt)].clear();
      pieceTypes &= ~piece_set(pt);
      // erase from promotion types to ensure consistency
      promotionPieceTypes[WHITE] &= ~piece_set(pt);
      promotionPieceTypes[BLACK] &= ~piece_set(pt);
  }

  void reset_pieces() {
      pieceToChar = std::string(PIECE_NB, ' ');
      pieceToCharSynonyms = std::string(PIECE_NB, ' ');
      pieceToSymbol.assign(PIECE_NB, "");
      pieceToSymbolSynonyms.assign(PIECE_NB, "");
      pieceTypes = NO_PIECE_SET;
      // clear promotion types to ensure consistency
      promotionPieceTypes[WHITE] = NO_PIECE_SET;
      promotionPieceTypes[BLACK] = NO_PIECE_SET;
  }

  // Reset values that always need to be redefined
  Variant* init() {
      nnueAlias = "";
      endgameEval = EG_EVAL_CHESS;
      return this;
  }

  Variant* conclude();
  void resolve_promotion_rules();
  void resolve_drop_regions();
  void resolve_baring_royal_types();
  void set_drop_region(Color c, Bitboard region, PieceType pt = NO_PIECE_TYPE) {
      if (pt == NO_PIECE_TYPE)
          dropRegion[c] = region;
      else
          dropRegionOverrides[c][pt] = {region, true};
  }
  void init_promotion_masks() const;
  Bitboard promotion_immobility_mask(Color c, PieceType pt, Bitboard walls) const;
  void set_optional_promotion_region(Color c, Bitboard region, PieceType pt = NO_PIECE_TYPE) {
      optionalPromotionRegions[c][pt] = {region, true, true};
      if (pt == NO_PIECE_TYPE)
          promotionRegion[c] = region; // Projection for inherited legacy INI options.
  }
  void set_mandatory_promotion_region(Color c, Bitboard region, PieceType pt = NO_PIECE_TYPE) {
      mandatoryPromotionRegions[c][pt] = {region, true, true};
      if (pt == NO_PIECE_TYPE)
          promotionRegion[c] = region;
  }
  // Replace a built-in's inherited shared region, keeping the intended kind
  // explicit at the definition. Independent per-piece overrides remain intact.
  void set_promotion_region(Color c, Bitboard region, PromotionRequirement requirement) {
      nativePromotionRequirement[c] = requirement;
      if (optionalPromotionRegions[c][NO_PIECE_TYPE].builtIn)
          optionalPromotionRegions[c][NO_PIECE_TYPE] = {};
      if (mandatoryPromotionRegions[c][NO_PIECE_TYPE].builtIn)
          mandatoryPromotionRegions[c][NO_PIECE_TYPE] = {};
      if (requirement == PROMOTION_OPTIONAL)
          set_optional_promotion_region(c, region);
      else
          set_mandatory_promotion_region(c, region);
  }
};

class VariantMap : public std::map<std::string, const Variant*> {
public:
  void init();
  template <bool DoCheck> void parse(std::string path);
  template <bool DoCheck> void parse_istream(std::istream& file);
  void clear_all();
  std::vector<std::string> get_keys();

private:
  void add(std::string s, Variant* v, bool configured = false);
};

extern VariantMap variants;

} // namespace Stockfish

#endif // #ifndef VARIANT_H_INCLUDED
