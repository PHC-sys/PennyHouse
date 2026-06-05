// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC721/ERC721.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/utils/Strings.sol";

contract AllowanceVault is ERC721 {

    using Strings for uint256;

    address public issuer;
    IERC20  public usdc;

    uint256 public totalMinted;
    uint256 public accumulated;
    bool    public minted;

    event Deposited(uint256 amount, uint256 total);
    event Claimed(address holder, uint256 amount);

    constructor(address _usdc)
        ERC721("EMILIO-BOND", "EMILIO")
    {
        issuer = msg.sender;
        usdc   = IERC20(_usdc);
    }

    // 토큰 이름 생성: EMILIO-BOND-001
    function tokenName(uint256 id) public pure returns (string memory) {
        string memory num;
        if (id < 10)        num = string(abi.encodePacked("00", id.toString()));
        else if (id < 100)  num = string(abi.encodePacked("0",  id.toString()));
        else                num = id.toString();
        return string(abi.encodePacked("EMILIO-BOND-", num));
    }

    // tokenURI → NFT 메타데이터
    function tokenURI(uint256 id) public pure override returns (string memory) {
        return string(abi.encodePacked(
            "data:application/json;utf8,{",
            '"name":"', tokenName(id), '",',
            '"description":"EMILIO Allowance Bond"',
            "}"
        ));
    }

    // 1. 특정 주소에게 NFT 발행
    function mintTo(address recipient) external returns (uint256) {
        require(msg.sender == issuer, "only issuer");
        require(!minted, "already minted");
        minted = true;
        totalMinted++;
        uint256 newId = totalMinted;
        _mint(recipient, newId);
        return newId;
    }

    // 2. 호찬님이 USDC 적립
    function deposit(uint256 amount) external {
        require(msg.sender == issuer, "only issuer");
        usdc.transferFrom(msg.sender, address(this), amount);
        accumulated += amount;
        emit Deposited(amount, accumulated);
    }

    // 3. NFT 소유자라면 누구든 claim
    function claim(uint256 id) external {
        require(ownerOf(id) == msg.sender, "not NFT owner");
        require(accumulated > 0, "nothing to claim");
        uint256 amount = accumulated;
        accumulated = 0;
        usdc.transfer(msg.sender, amount);
        emit Claimed(msg.sender, amount);
    }

    // 4. 잔액 확인
    function balance() external view returns (uint256) {
        return accumulated;
    }
}